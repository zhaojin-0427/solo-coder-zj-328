import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager
from .schemas import (
    ServiceItemCreate, ServiceItemUpdate, ServiceItem,
    MaterialSpec, SpecialNote, HistoryRecord,
    StatsItemMissRate, StatsTopErrorMaterial, StatsAgentDistribution, StatsOverall,
    ElderType, AgentRelation, MaterialCategory, PhotoSpec,
    PreReviewWorkOrder, PreReviewStatus, RiskLevel, ServiceWindow,
    OneTimeNoticeRecord
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "elder_service.db")


class DictEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (ElderType, AgentRelation, MaterialCategory, PhotoSpec)):
            return obj.value
        return super().default(obj)


def _parse_material_spec(data: dict) -> MaterialSpec:
    need_photo_spec = data.get("need_photo_spec")
    if need_photo_spec:
        need_photo_spec = PhotoSpec(need_photo_spec)
    return MaterialSpec(
        name=data["name"],
        category=MaterialCategory(data["category"]),
        required=data.get("required", True),
        need_original=data.get("need_original", True),
        need_copy=data.get("need_copy", 0),
        need_photo_spec=need_photo_spec,
        description=data.get("description", "")
    )


def _parse_special_note(data: dict) -> SpecialNote:
    extra = [_parse_material_spec(m) for m in data.get("extra_materials", [])]
    return SpecialNote(
        elder_type=ElderType(data["elder_type"]),
        note=data.get("note", ""),
        extra_materials=extra
    )


def _row_to_service_item(row: sqlite3.Row) -> ServiceItem:
    base = json.loads(row["base_materials"]) if row["base_materials"] else []
    agent = json.loads(row["agent_required_materials"]) if row["agent_required_materials"] else []
    special = json.loads(row["special_notes"]) if row["special_notes"] else []
    return ServiceItem(
        id=row["id"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        description=row["description"],
        base_materials=[_parse_material_spec(m) for m in base],
        agent_required_materials=[_parse_material_spec(m) for m in agent],
        special_notes=[_parse_special_note(n) for n in special],
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"])
    )


def _row_to_history(row: sqlite3.Row) -> HistoryRecord:
    return HistoryRecord(
        id=row["id"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        elder_type=row["elder_type"],
        is_agent=bool(row["is_agent"]),
        agent_relation=row["agent_relation"],
        is_pass=bool(row["is_pass"]),
        missing_count=row["missing_count"],
        missing_categories=row["missing_categories"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
        make_up_count=row["make_up_count"] or 0
    )


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS service_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_code TEXT UNIQUE NOT NULL,
                    item_name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    base_materials TEXT DEFAULT '[]',
                    agent_required_materials TEXT DEFAULT '[]',
                    special_notes TEXT DEFAULT '[]',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS verification_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_code TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    elder_type TEXT NOT NULL,
                    is_agent INTEGER DEFAULT 0,
                    agent_relation TEXT,
                    is_pass INTEGER DEFAULT 0,
                    missing_count INTEGER DEFAULT 0,
                    missing_categories TEXT DEFAULT '',
                    missing_details_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    make_up_count INTEGER DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS miss_material_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    history_id INTEGER NOT NULL,
                    material_category TEXT NOT NULL,
                    material_name TEXT NOT NULL,
                    missing_type TEXT NOT NULL,
                    FOREIGN KEY(history_id) REFERENCES verification_history(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS make_up_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    verification_id INTEGER NOT NULL,
                    item_code TEXT NOT NULL,
                    attempt_no INTEGER DEFAULT 1,
                    missing_before INTEGER DEFAULT 0,
                    missing_after INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(verification_id) REFERENCES verification_history(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS pre_review_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_order_no TEXT UNIQUE NOT NULL,
                    item_code TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    elder_type TEXT NOT NULL,
                    elder_id_card TEXT NOT NULL,
                    elder_name TEXT NOT NULL,
                    is_agent INTEGER DEFAULT 0,
                    agent_relation TEXT,
                    agent_name TEXT,
                    contact_phone TEXT NOT NULL,
                    expected_window TEXT,
                    appointment_date TEXT,
                    remarks TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    is_pass INTEGER DEFAULT 0,
                    total_required INTEGER DEFAULT 0,
                    total_missing INTEGER DEFAULT 0,
                    total_ready INTEGER DEFAULT 0,
                    one_time_notice TEXT DEFAULT '',
                    suggestion_deadline TEXT NOT NULL,
                    window_notes_json TEXT DEFAULT '[]',
                    missing_list_json TEXT DEFAULT '[]',
                    ready_materials_json TEXT DEFAULT '[]',
                    check_summary_json TEXT DEFAULT '{}',
                    is_duplicate INTEGER DEFAULT 0,
                    linked_original_id INTEGER,
                    review_count INTEGER DEFAULT 0,
                    supplement_count INTEGER DEFAULT 0,
                    reviewer TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_elder_id ON pre_review_orders(elder_id_card)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_phone ON pre_review_orders(contact_phone)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_item_code ON pre_review_orders(item_code)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_status ON pre_review_orders(status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_window ON pre_review_orders(expected_window)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_created ON pre_review_orders(created_at)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS pre_review_notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_order_id INTEGER NOT NULL,
                    work_order_no TEXT NOT NULL,
                    notice_type TEXT NOT NULL,
                    notice_content TEXT NOT NULL,
                    notice_method TEXT NOT NULL DEFAULT 'system',
                    notified_to TEXT NOT NULL,
                    notified_phone TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(work_order_id) REFERENCES pre_review_orders(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS pre_review_supplements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_order_id INTEGER NOT NULL,
                    work_order_no TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    review_result INTEGER NOT NULL,
                    missing_before INTEGER DEFAULT 0,
                    missing_after INTEGER DEFAULT 0,
                    review_remark TEXT,
                    supplemented_materials_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(work_order_id) REFERENCES pre_review_orders(id)
                )
            """)

    def _has_items(self) -> bool:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM service_items")
            return c.fetchone()["cnt"] > 0

    def seed_default_items(self, default_items: List[ServiceItemCreate]):
        if self._has_items():
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            c = conn.cursor()
            for item in default_items:
                c.execute("""
                    INSERT INTO service_items
                    (item_code, item_name, description, base_materials, agent_required_materials,
                     special_notes, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.item_code,
                    item.item_name,
                    item.description,
                    json.dumps([m.model_dump() for m in item.base_materials], cls=DictEncoder),
                    json.dumps([m.model_dump() for m in item.agent_required_materials], cls=DictEncoder),
                    json.dumps([n.model_dump() for n in item.special_notes], cls=DictEncoder),
                    1 if item.enabled else 0,
                    now,
                    now
                ))

    def list_items(self, enabled_only: bool = False) -> List[ServiceItem]:
        with self._connect() as conn:
            c = conn.cursor()
            sql = "SELECT * FROM service_items"
            if enabled_only:
                sql += " WHERE enabled = 1"
            sql += " ORDER BY id"
            c.execute(sql)
            return [_row_to_service_item(r) for r in c.fetchall()]

    def get_item(self, item_code: str) -> Optional[ServiceItem]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM service_items WHERE item_code = ?", (item_code,))
            row = c.fetchone()
            return _row_to_service_item(row) if row else None

    def create_item(self, data: ServiceItemCreate) -> ServiceItem:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO service_items
                (item_code, item_name, description, base_materials, agent_required_materials,
                 special_notes, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.item_code, data.item_name, data.description,
                json.dumps([m.model_dump() for m in data.base_materials], cls=DictEncoder),
                json.dumps([m.model_dump() for m in data.agent_required_materials], cls=DictEncoder),
                json.dumps([n.model_dump() for n in data.special_notes], cls=DictEncoder),
                1 if data.enabled else 0,
                now, now
            ))
            new_id = c.lastrowid
            c.execute("SELECT * FROM service_items WHERE id = ?", (new_id,))
            return _row_to_service_item(c.fetchone())

    def update_item(self, item_code: str, data: ServiceItemUpdate) -> Optional[ServiceItem]:
        existing = self.get_item(item_code)
        if not existing:
            return None
        now = datetime.now().isoformat()
        updates = []
        params = []
        if data.item_name is not None:
            updates.append("item_name = ?")
            params.append(data.item_name)
        if data.description is not None:
            updates.append("description = ?")
            params.append(data.description)
        if data.base_materials is not None:
            updates.append("base_materials = ?")
            params.append(json.dumps([m.model_dump() for m in data.base_materials], cls=DictEncoder))
        if data.agent_required_materials is not None:
            updates.append("agent_required_materials = ?")
            params.append(json.dumps([m.model_dump() for m in data.agent_required_materials], cls=DictEncoder))
        if data.special_notes is not None:
            updates.append("special_notes = ?")
            params.append(json.dumps([n.model_dump() for n in data.special_notes], cls=DictEncoder))
        if data.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if data.enabled else 0)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(item_code)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(f"UPDATE service_items SET {', '.join(updates)} WHERE item_code = ?", params)
        return self.get_item(item_code)

    def delete_item(self, item_code: str) -> bool:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM service_items WHERE item_code = ?", (item_code,))
            return c.rowcount > 0

    def save_verification(
        self,
        item_code: str,
        item_name: str,
        elder_type: str,
        is_agent: bool,
        agent_relation: Optional[str],
        is_pass: bool,
        missing_count: int,
        missing_categories: List[str],
        missing_details: List[Dict]
    ) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO verification_history
                (item_code, item_name, elder_type, is_agent, agent_relation,
                 is_pass, missing_count, missing_categories, missing_details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_code, item_name, elder_type,
                1 if is_agent else 0,
                agent_relation,
                1 if is_pass else 0,
                missing_count,
                json.dumps(missing_categories, ensure_ascii=False),
                json.dumps(missing_details, cls=DictEncoder, ensure_ascii=False),
                now
            ))
            history_id = c.lastrowid
            for md in missing_details:
                c.execute("""
                    INSERT INTO miss_material_details
                    (history_id, material_category, material_name, missing_type)
                    VALUES (?, ?, ?, ?)
                """, (
                    history_id,
                    md.get("category", "") if isinstance(md, dict) else getattr(md, "category", ""),
                    md.get("name", "") if isinstance(md, dict) else getattr(md, "name", ""),
                    md.get("missing_type", "") if isinstance(md, dict) else getattr(md, "missing_type", "")
                ))
            return history_id

    def record_make_up_attempt(
        self,
        verification_id: int,
        item_code: str,
        attempt_no: int,
        missing_before: int,
        missing_after: int
    ):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO make_up_attempts
                (verification_id, item_code, attempt_no, missing_before, missing_after, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (verification_id, item_code, attempt_no, missing_before, missing_after, now))
            c.execute("""
                UPDATE verification_history SET make_up_count = ? WHERE id = ?
            """, (attempt_no, verification_id))

    def list_history(
        self,
        item_code: Optional[str] = None,
        is_pass: Optional[bool] = None,
        is_agent: Optional[bool] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[HistoryRecord]:
        sql = "SELECT * FROM verification_history WHERE 1=1"
        params = []
        if item_code:
            sql += " AND item_code = ?"
            params.append(item_code)
        if is_pass is not None:
            sql += " AND is_pass = ?"
            params.append(1 if is_pass else 0)
        if is_agent is not None:
            sql += " AND is_agent = ?"
            params.append(1 if is_agent else 0)
        if start_date:
            sql += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            sql += " AND date(created_at) <= date(?)"
            params.append(end_date)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(sql, params)
            return [_row_to_history(r) for r in c.fetchall()]

    def get_history_detail(self, history_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM verification_history WHERE id = ?", (history_id,))
            row = c.fetchone()
            if not row:
                return None
            record = _row_to_history(row)
            details_json = json.loads(row["missing_details_json"]) if row["missing_details_json"] else []
            return {
                "record": record,
                "missing_details": details_json
            }

    def get_overall_stats(self, item_code: Optional[str] = None, limit_items: int = 10, limit_materials: int = 10) -> StatsOverall:
        with self._connect() as conn:
            c = conn.cursor()

            base_sql = "SELECT COUNT(*) as total, SUM(CASE WHEN is_pass = 0 THEN 1 ELSE 0 END) as miss_cnt, AVG(make_up_count) as avg_makeup FROM verification_history"
            params = []
            if item_code:
                base_sql += " WHERE item_code = ?"
                params.append(item_code)
            c.execute(base_sql, params)
            row = c.fetchone()
            total = row["total"] or 0
            miss_cnt = row["miss_cnt"] or 0
            avg_makeup = row["avg_makeup"] or 0.0
            overall_miss_rate = round(miss_cnt / total, 4) if total > 0 else 0.0

            item_sql = """
                SELECT si.item_code, si.item_name,
                       COUNT(vh.id) as total_queries,
                       SUM(CASE WHEN vh.is_pass = 1 THEN 1 ELSE 0 END) as pass_cnt,
                       SUM(CASE WHEN vh.is_pass = 0 THEN 1 ELSE 0 END) as miss_cnt
                FROM service_items si
                LEFT JOIN verification_history vh ON si.item_code = vh.item_code
            """
            iparams = []
            if item_code:
                item_sql += " WHERE si.item_code = ?"
                iparams.append(item_code)
            item_sql += " GROUP BY si.item_code ORDER BY miss_cnt DESC, total_queries DESC LIMIT ?"
            iparams.append(limit_items)
            c.execute(item_sql, iparams)
            top_items = []
            for r in c.fetchall():
                tq = r["total_queries"] or 0
                mc = r["miss_cnt"] or 0
                pc = r["pass_cnt"] or 0
                top_items.append(StatsItemMissRate(
                    item_code=r["item_code"],
                    item_name=r["item_name"],
                    total_queries=tq,
                    pass_count=pc,
                    miss_count=mc,
                    miss_rate=round(mc / tq, 4) if tq > 0 else 0.0
                ))

            c.execute("""
                SELECT material_category, material_name,
                       COUNT(*) as miss_count
                FROM miss_material_details
                GROUP BY material_category, material_name
                ORDER BY miss_count DESC LIMIT ?
            """, (limit_materials,))
            top_materials = []
            rank = 0
            for r in c.fetchall():
                rank += 1
                mc = r["miss_count"] or 0
                rate = round(mc / miss_cnt, 4) if miss_cnt > 0 else 0.0
                top_materials.append(StatsTopErrorMaterial(
                    category=r["material_category"],
                    name=r["material_name"],
                    miss_count=mc,
                    miss_rate=rate,
                    rank=rank
                ))

            c.execute("""
                SELECT agent_relation,
                       COUNT(*) as cnt,
                       AVG(missing_count) as avg_miss
                FROM verification_history
                WHERE is_agent = 1
                GROUP BY agent_relation
                ORDER BY cnt DESC
            """)
            agent_rows = c.fetchall()
            agent_total = sum(r["cnt"] for r in agent_rows) or 0
            agent_distribution = []
            for r in agent_rows:
                cnt = r["cnt"] or 0
                agent_distribution.append(StatsAgentDistribution(
                    agent_relation=r["agent_relation"] or "unknown",
                    count=cnt,
                    ratio=round(cnt / agent_total, 4) if agent_total > 0 else 0.0,
                    avg_miss_count=round(r["avg_miss"] or 0, 2)
                ))

            return StatsOverall(
                total_queries=total,
                overall_miss_rate=overall_miss_rate,
                avg_make_up_count=round(avg_makeup, 2),
                top_items=top_items,
                top_materials=top_materials,
                agent_distribution=agent_distribution
            )


def _row_to_pre_review_order(row: sqlite3.Row) -> PreReviewWorkOrder:
    return PreReviewWorkOrder(
        id=row["id"],
        work_order_no=row["work_order_no"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        elder_type=row["elder_type"],
        elder_id_card=row["elder_id_card"],
        elder_name=row["elder_name"],
        is_agent=bool(row["is_agent"]),
        agent_relation=row["agent_relation"],
        agent_name=row["agent_name"],
        contact_phone=row["contact_phone"],
        expected_window=row["expected_window"],
        appointment_date=row["appointment_date"],
        remarks=row["remarks"],
        status=row["status"],
        risk_level=row["risk_level"],
        is_pass=bool(row["is_pass"]),
        total_required=row["total_required"],
        total_missing=row["total_missing"],
        total_ready=row["total_ready"],
        one_time_notice=row["one_time_notice"],
        suggestion_deadline=datetime.fromisoformat(row["suggestion_deadline"]),
        window_notes=json.loads(row["window_notes_json"]) if row["window_notes_json"] else [],
        missing_list_json=row["missing_list_json"],
        ready_materials_json=row["ready_materials_json"],
        check_summary_json=row["check_summary_json"],
        is_duplicate=bool(row["is_duplicate"]),
        linked_original_id=row["linked_original_id"],
        review_count=row["review_count"],
        supplement_count=row["supplement_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        reviewer=row["reviewer"],
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None
    )


def _row_to_notice_record(row: sqlite3.Row) -> OneTimeNoticeRecord:
    return OneTimeNoticeRecord(
        id=row["id"],
        work_order_id=row["work_order_id"],
        work_order_no=row["work_order_no"],
        notice_type=row["notice_type"],
        notice_content=row["notice_content"],
        notice_method=row["notice_method"],
        notified_to=row["notified_to"],
        notified_phone=row["notified_phone"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


# Add these methods to Database class by appending below
def _generate_work_order_no(dt: datetime) -> str:
    return f"PR{dt.strftime('%Y%m%d%H%M%S')}{dt.microsecond // 1000:03d}"


def db_create_pre_review_order(
    self,
    item_code: str,
    item_name: str,
    elder_type: str,
    elder_id_card: str,
    elder_name: str,
    is_agent: bool,
    agent_relation: Optional[str],
    agent_name: Optional[str],
    contact_phone: str,
    expected_window: Optional[str],
    appointment_date: Optional[str],
    remarks: Optional[str],
    status: str,
    risk_level: str,
    is_pass: bool,
    total_required: int,
    total_missing: int,
    total_ready: int,
    one_time_notice: str,
    suggestion_deadline: datetime,
    window_notes: List[str],
    missing_list: List[Dict],
    ready_materials: List[Dict],
    check_summary: Dict,
    is_duplicate: bool = False,
    linked_original_id: Optional[int] = None
) -> PreReviewWorkOrder:
    now = datetime.now()
    work_order_no = _generate_work_order_no(now)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pre_review_orders
            (work_order_no, item_code, item_name, elder_type, elder_id_card, elder_name,
             is_agent, agent_relation, agent_name, contact_phone, expected_window,
             appointment_date, remarks, status, risk_level, is_pass, total_required,
             total_missing, total_ready, one_time_notice, suggestion_deadline,
             window_notes_json, missing_list_json, ready_materials_json, check_summary_json,
             is_duplicate, linked_original_id, review_count, supplement_count,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            work_order_no, item_code, item_name, elder_type, elder_id_card, elder_name,
            1 if is_agent else 0, agent_relation, agent_name, contact_phone, expected_window,
            appointment_date, remarks, status, risk_level, 1 if is_pass else 0, total_required,
            total_missing, total_ready, one_time_notice, suggestion_deadline.isoformat(),
            json.dumps(window_notes, ensure_ascii=False),
            json.dumps(missing_list, ensure_ascii=False),
            json.dumps(ready_materials, ensure_ascii=False),
            json.dumps(check_summary, ensure_ascii=False),
            1 if is_duplicate else 0, linked_original_id, 1 if is_pass else 0, 0,
            now.isoformat(), now.isoformat()
        ))
        new_id = c.lastrowid
        c.execute("SELECT * FROM pre_review_orders WHERE id = ?", (new_id,))
        return _row_to_pre_review_order(c.fetchone())


Database.create_pre_review_order = db_create_pre_review_order


def db_find_duplicate_orders(
    self,
    item_code: str,
    elder_id_card: Optional[str] = None,
    contact_phone: Optional[str] = None,
    days: int = 7
) -> List[PreReviewWorkOrder]:
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    sql = "SELECT * FROM pre_review_orders WHERE item_code = ? AND created_at >= ?"
    params = [item_code, cutoff]
    if elder_id_card and contact_phone:
        sql += " AND (elder_id_card = ? OR contact_phone = ?)"
        params.extend([elder_id_card, contact_phone])
    elif elder_id_card:
        sql += " AND elder_id_card = ?"
        params.append(elder_id_card)
    elif contact_phone:
        sql += " AND contact_phone = ?"
        params.append(contact_phone)
    sql += " ORDER BY created_at DESC"
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        return [_row_to_pre_review_order(r) for r in c.fetchall()]


Database.find_duplicate_orders = db_find_duplicate_orders


def db_get_pre_review_order(self, order_id: int) -> Optional[PreReviewWorkOrder]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM pre_review_orders WHERE id = ?", (order_id,))
        row = c.fetchone()
        return _row_to_pre_review_order(row) if row else None


Database.get_pre_review_order = db_get_pre_review_order


def db_get_pre_review_by_no(self, work_order_no: str) -> Optional[PreReviewWorkOrder]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM pre_review_orders WHERE work_order_no = ?", (work_order_no,))
        row = c.fetchone()
        return _row_to_pre_review_order(row) if row else None


Database.get_pre_review_by_no = db_get_pre_review_by_no


def db_list_pre_review_orders(
    self,
    item_code: Optional[str] = None,
    expected_window: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    elder_id_card: Optional[str] = None,
    contact_phone: Optional[str] = None,
    risk_level: Optional[str] = None,
    is_duplicate: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    sql = "SELECT * FROM pre_review_orders WHERE 1=1"
    count_sql = "SELECT COUNT(*) as cnt FROM pre_review_orders WHERE 1=1"
    params = []
    if item_code:
        sql += " AND item_code = ?"
        count_sql += " AND item_code = ?"
        params.append(item_code)
    if expected_window:
        sql += " AND expected_window = ?"
        count_sql += " AND expected_window = ?"
        params.append(expected_window)
    if status:
        sql += " AND status = ?"
        count_sql += " AND status = ?"
        params.append(status)
    if start_date:
        sql += " AND date(created_at) >= date(?)"
        count_sql += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        sql += " AND date(created_at) <= date(?)"
        count_sql += " AND date(created_at) <= date(?)"
        params.append(end_date)
    if elder_id_card:
        sql += " AND elder_id_card = ?"
        count_sql += " AND elder_id_card = ?"
        params.append(elder_id_card)
    if contact_phone:
        sql += " AND contact_phone = ?"
        count_sql += " AND contact_phone = ?"
        params.append(contact_phone)
    if risk_level:
        sql += " AND risk_level = ?"
        count_sql += " AND risk_level = ?"
        params.append(risk_level)
    if is_duplicate is not None:
        sql += " AND is_duplicate = ?"
        count_sql += " AND is_duplicate = ?"
        params.append(1 if is_duplicate else 0)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(count_sql, params)
        total = c.fetchone()["cnt"] or 0
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size
        full_params = params + [page_size, offset]
        c.execute(sql, full_params)
        items = [_row_to_pre_review_order(r) for r in c.fetchall()]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items
    }


Database.list_pre_review_orders = db_list_pre_review_orders


def db_update_pre_review_status(
    self,
    order_id: int,
    status: str,
    reviewer: Optional[str] = None,
    review_remark: Optional[str] = None
) -> Optional[PreReviewWorkOrder]:
    existing = self.get_pre_review_order(order_id)
    if not existing:
        return None
    now = datetime.now()
    updates = ["status = ?", "updated_at = ?", "review_count = review_count + 1"]
    params = [status, now.isoformat()]
    if reviewer:
        updates.append("reviewer = ?")
        params.append(reviewer)
        updates.append("reviewed_at = ?")
        params.append(now.isoformat())
    params.append(order_id)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE pre_review_orders SET {', '.join(updates)} WHERE id = ?", params)
    return self.get_pre_review_order(order_id)


Database.update_pre_review_status = db_update_pre_review_status


def db_update_pre_review_order(
    self,
    order_id: int,
    updates_dict: Dict[str, Any]
) -> Optional[PreReviewWorkOrder]:
    existing = self.get_pre_review_order(order_id)
    if not existing:
        return None
    now = datetime.now()
    updates = ["updated_at = ?"]
    params = [now.isoformat()]
    json_fields = ["window_notes", "missing_list", "ready_materials", "check_summary"]
    for key, value in updates_dict.items():
        if key in json_fields:
            col = f"{key}_json"
            updates.append(f"{col} = ?")
            params.append(json.dumps(value, ensure_ascii=False))
        elif key == "suggestion_deadline":
            updates.append("suggestion_deadline = ?")
            params.append(value.isoformat() if isinstance(value, datetime) else value)
        elif key == "is_pass":
            updates.append("is_pass = ?")
            params.append(1 if value else 0)
        elif key == "is_agent":
            updates.append("is_agent = ?")
            params.append(1 if value else 0)
        elif key == "is_duplicate":
            updates.append("is_duplicate = ?")
            params.append(1 if value else 0)
        elif key not in ("id", "work_order_no", "created_at"):
            updates.append(f"{key} = ?")
            params.append(value)
    params.append(order_id)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE pre_review_orders SET {', '.join(updates)} WHERE id = ?", params)
    return self.get_pre_review_order(order_id)


Database.update_pre_review_order = db_update_pre_review_order


def db_create_notice_record(
    self,
    work_order_id: int,
    work_order_no: str,
    notice_type: str,
    notice_content: str,
    notice_method: str,
    notified_to: str,
    notified_phone: str
) -> OneTimeNoticeRecord:
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pre_review_notices
            (work_order_id, work_order_no, notice_type, notice_content, notice_method,
             notified_to, notified_phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            work_order_id, work_order_no, notice_type, notice_content, notice_method,
            notified_to, notified_phone, now.isoformat()
        ))
        new_id = c.lastrowid
        c.execute("SELECT * FROM pre_review_notices WHERE id = ?", (new_id,))
        return _row_to_notice_record(c.fetchone())


Database.create_notice_record = db_create_notice_record


def db_list_notice_records(
    self,
    work_order_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notice_method: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[OneTimeNoticeRecord]:
    sql = "SELECT * FROM pre_review_notices WHERE 1=1"
    params = []
    if work_order_id:
        sql += " AND work_order_id = ?"
        params.append(work_order_id)
    if start_date:
        sql += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        sql += " AND date(created_at) <= date(?)"
        params.append(end_date)
    if notice_method:
        sql += " AND notice_method = ?"
        params.append(notice_method)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        return [_row_to_notice_record(r) for r in c.fetchall()]


Database.list_notice_records = db_list_notice_records


def db_create_supplement_review(
    self,
    work_order_id: int,
    work_order_no: str,
    reviewer: str,
    review_result: bool,
    missing_before: int,
    missing_after: int,
    review_remark: Optional[str] = None,
    supplemented_materials: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pre_review_supplements
            (work_order_id, work_order_no, reviewer, review_result, missing_before,
             missing_after, review_remark, supplemented_materials_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            work_order_id, work_order_no, reviewer, 1 if review_result else 0,
            missing_before, missing_after, review_remark or "",
            json.dumps(supplemented_materials or [], ensure_ascii=False),
            now.isoformat()
        ))
        c.execute("""
            UPDATE pre_review_orders SET supplement_count = supplement_count + 1, updated_at = ? WHERE id = ?
        """, (now.isoformat(), work_order_id))
        return {
            "id": c.lastrowid,
            "work_order_id": work_order_id,
            "work_order_no": work_order_no,
            "created_at": now.isoformat()
        }


Database.create_supplement_review = db_create_supplement_review


def db_list_supplement_records(self, work_order_id: int) -> List[Dict[str, Any]]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM pre_review_supplements WHERE work_order_id = ? ORDER BY created_at DESC
        """, (work_order_id,))
        records = []
        for r in c.fetchall():
            records.append({
                "id": r["id"],
                "work_order_id": r["work_order_id"],
                "work_order_no": r["work_order_no"],
                "reviewer": r["reviewer"],
                "review_result": bool(r["review_result"]),
                "missing_before": r["missing_before"],
                "missing_after": r["missing_after"],
                "review_remark": r["review_remark"],
                "supplemented_materials": json.loads(r["supplemented_materials_json"]) if r["supplemented_materials_json"] else [],
                "created_at": r["created_at"]
            })
        return records


Database.list_supplement_records = db_list_supplement_records


def db_get_linked_orders(self, elder_id_card: Optional[str] = None, contact_phone: Optional[str] = None, item_code: Optional[str] = None, exclude_id: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = "SELECT id, work_order_no, item_code, item_name, status, is_pass, total_missing, created_at FROM pre_review_orders WHERE 1=1"
    params = []
    if elder_id_card:
        sql += " AND elder_id_card = ?"
        params.append(elder_id_card)
    elif contact_phone:
        sql += " AND contact_phone = ?"
        params.append(contact_phone)
    if item_code:
        sql += " AND item_code = ?"
        params.append(item_code)
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " ORDER BY created_at DESC LIMIT 20"
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        return [dict(r) for r in c.fetchall()]


Database.get_linked_orders = db_get_linked_orders


def db_get_pre_review_stats(
    self,
    item_code: Optional[str] = None,
    expected_window: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    base_sql = "SELECT COUNT(*) as total FROM pre_review_orders WHERE 1=1"
    params = []
    if item_code:
        base_sql += " AND item_code = ?"
        params.append(item_code)
    if expected_window:
        base_sql += " AND expected_window = ?"
        params.append(expected_window)
    if start_date:
        base_sql += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        base_sql += " AND date(created_at) <= date(?)"
        params.append(end_date)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(base_sql, params)
        total_orders = c.fetchone()["total"] or 0

        pass_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as pass_cnt") + " AND is_pass = 1"
        c.execute(pass_sql, params)
        pass_count = c.fetchone()["pass_cnt"] or 0

        dup_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as dup_cnt") + " AND is_duplicate = 1"
        c.execute(dup_sql, params)
        duplicate_count = c.fetchone()["dup_cnt"] or 0

        avg_sql = base_sql.replace("COUNT(*) as total", "AVG(total_missing) as avg_miss")
        c.execute(avg_sql, params)
        avg_missing = round(c.fetchone()["avg_miss"] or 0.0, 2)

        exp_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as exp_cnt") + " AND status = 'expired'"
        c.execute(exp_sql, params)
        expired_count = c.fetchone()["exp_cnt"] or 0

        supp_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as supp_cnt") + " AND status IN ('supplementing','pending') AND supplement_count > 0"
        c.execute(supp_sql, params)
        supplement_in_progress_count = c.fetchone()["supp_cnt"] or 0

        item_miss_sql = """
            SELECT si.item_code, si.item_name,
                   COUNT(pr.id) as order_count,
                   AVG(pr.total_missing) as avg_miss
            FROM service_items si
            LEFT JOIN pre_review_orders pr ON si.item_code = pr.item_code
            WHERE 1=1
        """
        iparams = []
        if expected_window:
            item_miss_sql += " AND pr.expected_window = ?"
            iparams.append(expected_window)
        if start_date:
            item_miss_sql += " AND date(pr.created_at) >= date(?)"
            iparams.append(start_date)
        if end_date:
            item_miss_sql += " AND date(pr.created_at) <= date(?)"
            iparams.append(end_date)
        item_miss_sql += " GROUP BY si.item_code ORDER BY order_count DESC, avg_miss DESC LIMIT 20"
        c.execute(item_miss_sql, iparams)
        item_avg_missing = []
        for r in c.fetchall():
            item_avg_missing.append({
                "item_code": r["item_code"],
                "item_name": r["item_name"],
                "order_count": r["order_count"] or 0,
                "avg_missing_count": round(r["avg_miss"] or 0.0, 2)
            })

        mat_combo_sql = """
            SELECT pr.missing_list_json, COUNT(*) as cnt
            FROM pre_review_orders pr
            WHERE pr.is_pass = 0 AND pr.missing_list_json != '[]'
        """
        mparams = []
        if item_code:
            mat_combo_sql += " AND pr.item_code = ?"
            mparams.append(item_code)
        if expected_window:
            mat_combo_sql += " AND pr.expected_window = ?"
            mparams.append(expected_window)
        if start_date:
            mat_combo_sql += " AND date(pr.created_at) >= date(?)"
            mparams.append(start_date)
        if end_date:
            mat_combo_sql += " AND date(pr.created_at) <= date(?)"
            mparams.append(end_date)
        mat_combo_sql += " GROUP BY pr.missing_list_json ORDER BY cnt DESC LIMIT 10"
        c.execute(mat_combo_sql, mparams)
        top_combos = []
        rank = 0
        for r in c.fetchall():
            rank += 1
            try:
                missing_list = json.loads(r["missing_list_json"]) if r["missing_list_json"] else []
                mat_names = " + ".join([m.get("name", m.get("material_name", "?")) for m in missing_list[:5]])
                if len(missing_list) > 5:
                    mat_names += f" 等{len(missing_list)}项"
            except Exception:
                mat_names = "材料组合"
            top_combos.append({
                "rank": rank,
                "combo_count": r["cnt"],
                "materials_preview": mat_names,
                "materials_count": len(missing_list) if 'missing_list' in locals() else 0
            })

        window_pass_sql = """
            SELECT expected_window,
                   COUNT(*) as total,
                   SUM(CASE WHEN is_pass = 1 THEN 1 ELSE 0 END) as pass_cnt
            FROM pre_review_orders
            WHERE expected_window IS NOT NULL
        """
        wparams = []
        if item_code:
            window_pass_sql += " AND item_code = ?"
            wparams.append(item_code)
        if start_date:
            window_pass_sql += " AND date(created_at) >= date(?)"
            wparams.append(start_date)
        if end_date:
            window_pass_sql += " AND date(created_at) <= date(?)"
            wparams.append(end_date)
        window_pass_sql += " GROUP BY expected_window ORDER BY total DESC"
        c.execute(window_pass_sql, wparams)
        window_pass_rates = []
        for r in c.fetchall():
            total = r["total"] or 0
            pass_cnt = r["pass_cnt"] or 0
            window_pass_rates.append({
                "window": r["expected_window"],
                "total_orders": total,
                "pass_count": pass_cnt,
                "pass_rate": round(pass_cnt / total, 4) if total > 0 else 0.0
            })

    return {
        "total_orders": total_orders,
        "pass_count": pass_count,
        "pass_rate": round(pass_count / total_orders, 4) if total_orders > 0 else 0.0,
        "duplicate_count": duplicate_count,
        "duplicate_rate": round(duplicate_count / total_orders, 4) if total_orders > 0 else 0.0,
        "avg_missing_count": avg_missing,
        "expired_count": expired_count,
        "supplement_in_progress_count": supplement_in_progress_count,
        "item_avg_missing": item_avg_missing,
        "top_return_material_combos": top_combos,
        "window_pass_rates": window_pass_rates
    }


Database.get_pre_review_stats = db_get_pre_review_stats
