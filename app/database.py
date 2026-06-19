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
    ElderType, AgentRelation, MaterialCategory, PhotoSpec
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
