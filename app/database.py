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
    OneTimeNoticeRecord,
    CompanionResource, CompanionResourceCreate, CompanionResourceUpdate,
    AccompanyAppointment, MatchedCompanion, AccompanyFollowUpRecord,
    AccompanyStatsCommunity, AccompanyStatsRiskCoverage,
    AccompanyStatsCompanionWorkload, AccompanyStatsMaterialFailure,
    AccompanyStatsOverall,
    ExceptionDisposalOrder, ExceptionProcessingRecord, ExceptionStatusHistory,
    ExceptionStatsItemRank, ExceptionStatsTypeAvgDuration, ExceptionStatsFailureReason,
    ExceptionStatsOverall, ExceptionType, ExceptionStatus, DisposalPriority,
    ResponsibleRole
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "elder_service.db")


class DictEncoder(json.JSONEncoder):
    def default(self, obj):
        from .schemas import (
            MobilityLevel, AccompanyDemandType, CompanionType,
            AppointmentStatus, ConfirmStatus,
            ExceptionType, ExceptionStatus, DisposalPriority,
            ResponsibleRole, ExceptionSourceType
        )
        if isinstance(obj, (
            ElderType, AgentRelation, MaterialCategory, PhotoSpec,
            MobilityLevel, AccompanyDemandType, CompanionType,
            AppointmentStatus, ConfirmStatus, RiskLevel, ServiceWindow,
            ExceptionType, ExceptionStatus, DisposalPriority,
            ResponsibleRole, ExceptionSourceType
        )):
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
            c.execute("""
                CREATE TABLE IF NOT EXISTS companion_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    companion_type TEXT NOT NULL,
                    community TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    id_card TEXT,
                    available_windows_json TEXT DEFAULT '[]',
                    eligible_items_json TEXT DEFAULT '[]',
                    max_daily_count INTEGER DEFAULT 3,
                    skills_json TEXT DEFAULT '[]',
                    is_active INTEGER DEFAULT 1,
                    remarks TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_cr_community ON companion_resources(community)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_cr_type ON companion_resources(companion_type)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_cr_active ON companion_resources(is_active)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS accompany_appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_no TEXT UNIQUE NOT NULL,
                    elder_name TEXT NOT NULL,
                    elder_type TEXT NOT NULL,
                    item_code TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    mobility_level TEXT NOT NULL,
                    is_living_alone INTEGER DEFAULT 0,
                    accompany_demand_type TEXT NOT NULL,
                    expected_date TEXT NOT NULL,
                    community TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    special_notes TEXT,
                    pre_review_order_id INTEGER,
                    verify_history_id INTEGER,
                    expected_window TEXT,
                    status TEXT NOT NULL DEFAULT 'pending_match',
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    missing_materials_json TEXT DEFAULT '[]',
                    match_priority INTEGER DEFAULT 3,
                    recommended_companion_id INTEGER,
                    recommended_companion_name TEXT,
                    recommended_companion_type TEXT,
                    recommended_companion_phone TEXT,
                    expected_service_period TEXT,
                    material_reminders_json TEXT DEFAULT '[]',
                    route_hints_json TEXT DEFAULT '[]',
                    risk_alerts_json TEXT DEFAULT '[]',
                    confirm_status TEXT NOT NULL DEFAULT 'unconfirmed',
                    cancel_reason TEXT,
                    cancel_remark TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_aa_community ON accompany_appointments(community)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_aa_item_code ON accompany_appointments(item_code)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_aa_status ON accompany_appointments(status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_aa_expected_date ON accompany_appointments(expected_date)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_aa_companion ON accompany_appointments(recommended_companion_id)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_aa_created ON accompany_appointments(created_at)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS accompany_match_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER NOT NULL,
                    companion_id INTEGER NOT NULL,
                    match_priority INTEGER NOT NULL,
                    match_score REAL NOT NULL,
                    match_reasons_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(appointment_id) REFERENCES accompany_appointments(id),
                    FOREIGN KEY(companion_id) REFERENCES companion_resources(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS accompany_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER NOT NULL,
                    appointment_no TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    operator TEXT,
                    remark TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(appointment_id) REFERENCES accompany_appointments(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS accompany_follow_ups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER NOT NULL,
                    appointment_no TEXT NOT NULL,
                    is_companion_arrived INTEGER NOT NULL,
                    is_elder_satisfied INTEGER NOT NULL,
                    materials_completed INTEGER NOT NULL,
                    failed_materials_json TEXT DEFAULT '[]',
                    service_duration_minutes INTEGER DEFAULT 0,
                    issues_json TEXT DEFAULT '[]',
                    suggestions TEXT,
                    follower TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(appointment_id) REFERENCES accompany_appointments(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS exception_disposal_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exception_no TEXT UNIQUE NOT NULL,
                    exception_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    item_code TEXT,
                    item_name TEXT,
                    elder_name TEXT,
                    elder_type TEXT,
                    community TEXT,
                    expected_window TEXT,
                    reporter TEXT NOT NULL,
                    reporter_role TEXT NOT NULL,
                    reporter_phone TEXT,
                    description TEXT NOT NULL,
                    location TEXT,
                    impact_completion INTEGER DEFAULT 1,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT NOT NULL DEFAULT 'p3_medium',
                    responsible_role TEXT NOT NULL DEFAULT 'supervisor',
                    responsible_person TEXT,
                    responsible_phone TEXT,
                    suggested_actions_json TEXT DEFAULT '[]',
                    latest_deadline TEXT NOT NULL,
                    follow_up_required INTEGER DEFAULT 1,
                    follow_up_deadline TEXT,
                    evidence_images_json TEXT DEFAULT '[]',
                    extra_info_json TEXT DEFAULT '{}',
                    closed_at TEXT,
                    closed_by TEXT,
                    close_remark TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_status ON exception_disposal_orders(status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_type ON exception_disposal_orders(exception_type)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_item ON exception_disposal_orders(item_code)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_community ON exception_disposal_orders(community)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_window ON exception_disposal_orders(expected_window)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_priority ON exception_disposal_orders(priority)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_responsible ON exception_disposal_orders(responsible_person)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_exc_created ON exception_disposal_orders(created_at)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS exception_processing_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exception_id INTEGER NOT NULL,
                    processor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    next_step TEXT,
                    duration_minutes INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(exception_id) REFERENCES exception_disposal_orders(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS exception_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exception_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    remark TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(exception_id) REFERENCES exception_disposal_orders(id)
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


def db_mark_expired_orders(self) -> int:
    now_iso = datetime.now().isoformat()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE pre_review_orders
            SET status = 'expired', updated_at = ?
            WHERE status NOT IN ('passed', 'completed', 'expired', 'rejected')
              AND is_pass = 0
              AND suggestion_deadline < ?
        """, (now_iso, now_iso))
        return c.rowcount


Database.mark_expired_orders = db_mark_expired_orders


def db_get_pre_review_stats(
    self,
    item_code: Optional[str] = None,
    expected_window: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    self.mark_expired_orders()

    now_iso = datetime.now().isoformat()
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

        exp_sql = base_sql.replace("COUNT(*) as total", "COUNT(*) as exp_cnt") + " AND is_pass = 0 AND suggestion_deadline < ?"
        exp_params = params + [now_iso]
        c.execute(exp_sql, exp_params)
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


def _row_to_companion_resource(row: sqlite3.Row) -> CompanionResource:
    return CompanionResource(
        id=row["id"],
        name=row["name"],
        companion_type=row["companion_type"],
        community=row["community"],
        phone=row["phone"],
        id_card=row["id_card"],
        available_windows=json.loads(row["available_windows_json"]) if row["available_windows_json"] else [],
        eligible_items=json.loads(row["eligible_items_json"]) if row["eligible_items_json"] else [],
        max_daily_count=row["max_daily_count"],
        skills=json.loads(row["skills_json"]) if row["skills_json"] else [],
        is_active=bool(row["is_active"]),
        remarks=row["remarks"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"])
    )


def _row_to_accompany_appointment(row: sqlite3.Row) -> AccompanyAppointment:
    return AccompanyAppointment(
        id=row["id"],
        appointment_no=row["appointment_no"],
        elder_name=row["elder_name"],
        elder_type=row["elder_type"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        mobility_level=row["mobility_level"],
        is_living_alone=bool(row["is_living_alone"]),
        accompany_demand_type=row["accompany_demand_type"],
        expected_date=row["expected_date"],
        community=row["community"],
        contact_phone=row["contact_phone"],
        special_notes=row["special_notes"],
        pre_review_order_id=row["pre_review_order_id"],
        verify_history_id=row["verify_history_id"],
        expected_window=row["expected_window"],
        status=row["status"],
        risk_level=row["risk_level"],
        missing_materials=json.loads(row["missing_materials_json"]) if row["missing_materials_json"] else [],
        match_priority=row["match_priority"],
        recommended_companion_id=row["recommended_companion_id"],
        recommended_companion_name=row["recommended_companion_name"],
        recommended_companion_type=row["recommended_companion_type"],
        recommended_companion_phone=row["recommended_companion_phone"],
        expected_service_period=row["expected_service_period"],
        material_reminders=json.loads(row["material_reminders_json"]) if row["material_reminders_json"] else [],
        route_hints=json.loads(row["route_hints_json"]) if row["route_hints_json"] else [],
        risk_alerts=json.loads(row["risk_alerts_json"]) if row["risk_alerts_json"] else [],
        confirm_status=row["confirm_status"],
        cancel_reason=row["cancel_reason"],
        cancel_remark=row["cancel_remark"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"])
    )


def _row_to_follow_up(row: sqlite3.Row) -> AccompanyFollowUpRecord:
    return AccompanyFollowUpRecord(
        id=row["id"],
        appointment_id=row["appointment_id"],
        appointment_no=row["appointment_no"],
        is_companion_arrived=bool(row["is_companion_arrived"]),
        is_elder_satisfied=bool(row["is_elder_satisfied"]),
        materials_completed=bool(row["materials_completed"]),
        failed_materials=json.loads(row["failed_materials_json"]) if row["failed_materials_json"] else [],
        service_duration_minutes=row["service_duration_minutes"],
        issues=json.loads(row["issues_json"]) if row["issues_json"] else [],
        suggestions=row["suggestions"],
        follower=row["follower"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


def _generate_appointment_no(dt: datetime) -> str:
    return f"AC{dt.strftime('%Y%m%d%H%M%S')}{dt.microsecond // 1000:03d}"


def db_create_companion_resource(self, data: CompanionResourceCreate) -> CompanionResource:
    now = datetime.now().isoformat()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO companion_resources
            (name, companion_type, community, phone, id_card, available_windows_json,
             eligible_items_json, max_daily_count, skills_json, is_active, remarks,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.name, data.companion_type.value, data.community, data.phone, data.id_card,
            json.dumps([w.value for w in data.available_windows], cls=DictEncoder, ensure_ascii=False),
            json.dumps(data.eligible_items, ensure_ascii=False),
            data.max_daily_count,
            json.dumps(data.skills, ensure_ascii=False),
            1 if data.is_active else 0,
            data.remarks,
            now, now
        ))
        new_id = c.lastrowid
        c.execute("SELECT * FROM companion_resources WHERE id = ?", (new_id,))
        return _row_to_companion_resource(c.fetchone())


Database.create_companion_resource = db_create_companion_resource


def db_get_companion_resource(self, resource_id: int) -> Optional[CompanionResource]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM companion_resources WHERE id = ?", (resource_id,))
        row = c.fetchone()
        return _row_to_companion_resource(row) if row else None


Database.get_companion_resource = db_get_companion_resource


def db_list_companion_resources(
    self,
    community: Optional[str] = None,
    companion_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    sql = "SELECT * FROM companion_resources WHERE 1=1"
    count_sql = "SELECT COUNT(*) as cnt FROM companion_resources WHERE 1=1"
    params = []
    if community:
        sql += " AND community = ?"
        count_sql += " AND community = ?"
        params.append(community)
    if companion_type:
        sql += " AND companion_type = ?"
        count_sql += " AND companion_type = ?"
        params.append(companion_type)
    if is_active is not None:
        sql += " AND is_active = ?"
        count_sql += " AND is_active = ?"
        params.append(1 if is_active else 0)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(count_sql, params)
        total = c.fetchone()["cnt"] or 0
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size
        full_params = params + [page_size, offset]
        c.execute(sql, full_params)
        items = [_row_to_companion_resource(r) for r in c.fetchall()]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items
    }


Database.list_companion_resources = db_list_companion_resources


def db_update_companion_resource(
    self,
    resource_id: int,
    data: CompanionResourceUpdate
) -> Optional[CompanionResource]:
    existing = self.get_companion_resource(resource_id)
    if not existing:
        return None
    now = datetime.now().isoformat()
    updates = ["updated_at = ?"]
    params = [now]
    if data.name is not None:
        updates.append("name = ?")
        params.append(data.name)
    if data.companion_type is not None:
        updates.append("companion_type = ?")
        params.append(data.companion_type.value)
    if data.community is not None:
        updates.append("community = ?")
        params.append(data.community)
    if data.phone is not None:
        updates.append("phone = ?")
        params.append(data.phone)
    if data.id_card is not None:
        updates.append("id_card = ?")
        params.append(data.id_card)
    if data.available_windows is not None:
        updates.append("available_windows_json = ?")
        params.append(json.dumps([w.value for w in data.available_windows], cls=DictEncoder, ensure_ascii=False))
    if data.eligible_items is not None:
        updates.append("eligible_items_json = ?")
        params.append(json.dumps(data.eligible_items, ensure_ascii=False))
    if data.max_daily_count is not None:
        updates.append("max_daily_count = ?")
        params.append(data.max_daily_count)
    if data.skills is not None:
        updates.append("skills_json = ?")
        params.append(json.dumps(data.skills, ensure_ascii=False))
    if data.is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if data.is_active else 0)
    if data.remarks is not None:
        updates.append("remarks = ?")
        params.append(data.remarks)
    params.append(resource_id)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE companion_resources SET {', '.join(updates)} WHERE id = ?", params)
    return self.get_companion_resource(resource_id)


Database.update_companion_resource = db_update_companion_resource


def db_delete_companion_resource(self, resource_id: int) -> bool:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM companion_resources WHERE id = ?", (resource_id,))
        return c.rowcount > 0


Database.delete_companion_resource = db_delete_companion_resource


def _calculate_risk_level(
    elder_type: str,
    mobility_level: str,
    is_living_alone: bool,
    missing_count: int
) -> str:
    score = 0
    if elder_type in ("special_elder", "disabled", "low_income"):
        score += 2
    if mobility_level == "bedridden":
        score += 3
    elif mobility_level == "wheelchair":
        score += 2
    elif mobility_level == "need_assist":
        score += 1
    if is_living_alone:
        score += 2
    if missing_count >= 3:
        score += 2
    elif missing_count >= 1:
        score += 1
    if score >= 6:
        return "critical"
    elif score >= 4:
        return "high"
    elif score >= 2:
        return "medium"
    else:
        return "low"


def _calculate_match_priority(risk_level: str, is_living_alone: bool) -> int:
    if risk_level == "critical":
        return 1
    elif risk_level == "high" or is_living_alone:
        return 2
    else:
        return 3


def _match_companions(
    self,
    community: str,
    item_code: str,
    expected_window: Optional[str],
    risk_level: str,
    expected_date: str,
    limit: int = 5
) -> List[MatchedCompanion]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT cr.*,
                   (SELECT COUNT(*) FROM accompany_appointments aa
                    WHERE aa.recommended_companion_id = cr.id
                      AND aa.expected_date = ?
                      AND aa.status NOT IN ('cancelled', 'no_show')) as daily_count
            FROM companion_resources cr
            WHERE cr.is_active = 1
              AND cr.community = ?
              AND (cr.eligible_items_json = '[]' OR cr.eligible_items_json LIKE ?)
        """, (expected_date, community, f'%"{item_code}"%'))
        candidates = []
        for row in c.fetchall():
            score = 0.0
            reasons = []
            cr_type = row["companion_type"]
            if risk_level in ("high", "critical") and cr_type == "social_worker":
                score += 30
                reasons.append("社工资质适合高风险老人")
            elif cr_type == "volunteer":
                score += 15
                reasons.append("社区志愿者")
            elif cr_type == "family":
                score += 20
                reasons.append("家属陪同")
            eligible = json.loads(row["eligible_items_json"]) if row["eligible_items_json"] else []
            if item_code in eligible:
                score += 25
                reasons.append(f"具备{item_code}事项陪同经验")
            windows = json.loads(row["available_windows_json"]) if row["available_windows_json"] else []
            if expected_window and expected_window in windows:
                score += 20
                reasons.append(f"可服务于{expected_window}窗口")
            elif not windows:
                score += 10
                reasons.append("无窗口限制")
            daily_count = row["daily_count"] or 0
            max_daily = row["max_daily_count"] or 3
            if daily_count < max_daily:
                score += 15
                reasons.append(f"当日尚有{max_daily - daily_count}个服务名额")
            else:
                score -= 20
                reasons.append("当日服务名额已满")
            candidates.append({
                "row": row,
                "score": score,
                "reasons": reasons
            })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        results = []
        for idx, cand in enumerate(candidates[:limit]):
            r = cand["row"]
            results.append(MatchedCompanion(
                companion_id=r["id"],
                companion_name=r["name"],
                companion_type=r["companion_type"],
                phone=r["phone"],
                community=r["community"],
                match_priority=idx + 1,
                match_score=round(cand["score"], 2),
                match_reasons=cand["reasons"]
            ))
        return results


Database._match_companions = _match_companions


def _generate_material_reminders(
    self,
    missing_materials: List[Dict[str, Any]],
    item_code: str
) -> List[str]:
    reminders = []
    item = self.get_item(item_code)
    if item:
        all_mats = item.base_materials + item.agent_required_materials
        for m in all_mats:
            if m.required:
                reminders.append(f"请务必携带：{m.name}" + (f"（需原件{m.need_original and '、复印件×' + str(m.need_copy) if m.need_copy > 0 else ''}）" if m.need_original or m.need_copy > 0 else ""))
    for mm in missing_materials:
        reminders.append(f"注意：上次预审缺件【{mm.get('name', '未知材料')}】，请务必补齐")
    if not reminders:
        reminders.append("请携带身份证等基础证件前往")
    return reminders


Database._generate_material_reminders = _generate_material_reminders


def _generate_route_hints(self, community: str, expected_window: Optional[str]) -> List[str]:
    hints = [
        f"从{community}出发，建议提前30分钟到达服务中心",
        "请携带老年卡或身份证以便取号排队"
    ]
    if expected_window:
        window_names = {
            "medical_window": "医保窗口",
            "social_security_window": "社保窗口",
            "banking_window": "银行窗口",
            "civil_affairs_window": "民政窗口",
            "comprehensive_window": "综合窗口",
            "registration_window": "登记窗口"
        }
        hints.append(f"办理窗口：{window_names.get(expected_window, expected_window)}，位于服务大厅一层")
    hints.append("服务中心配备无障碍通道和轮椅租借服务")
    return hints


Database._generate_route_hints = _generate_route_hints


def _generate_risk_alerts(
    self,
    risk_level: str,
    mobility_level: str,
    is_living_alone: bool,
    missing_count: int
) -> List[str]:
    alerts = []
    if risk_level == "critical":
        alerts.append("【紧急】该老人为极高风险人群，需安排专业社工陪同")
    elif risk_level == "high":
        alerts.append("【重要】该老人为高风险人群，建议优先派单")
    if mobility_level == "bedridden":
        alerts.append("老人卧床，需安排上门接送服务")
    elif mobility_level == "wheelchair":
        alerts.append("老人使用轮椅，需安排无障碍路线和志愿者协助")
    elif mobility_level == "need_assist":
        alerts.append("老人行动不便，需有人搀扶协助")
    if is_living_alone:
        alerts.append("老人独居，需特别关注其安全状态")
    if missing_count > 0:
        alerts.append(f"存在{missing_count}项缺件，需提醒老人或家属提前补齐材料")
    return alerts


Database._generate_risk_alerts = _generate_risk_alerts


def db_create_accompany_appointment(
    self,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    item = self.get_item(data["item_code"])
    if not item:
        raise ValueError(f"事项编码 {data['item_code']} 不存在")
    item_name = item.item_name
    missing_materials = []
    missing_count = 0
    if data.get("pre_review_order_id"):
        pr_order = self.get_pre_review_order(data["pre_review_order_id"])
        if pr_order:
            missing_list = json.loads(pr_order.missing_list_json) if pr_order.missing_list_json else []
            missing_materials = missing_list
            missing_count = pr_order.total_missing
    elif data.get("verify_history_id"):
        hd = self.get_history_detail(data["verify_history_id"])
        if hd:
            missing_materials = hd.get("missing_details", [])
            missing_count = len(missing_materials)
    risk_level = _calculate_risk_level(
        data["elder_type"].value if hasattr(data["elder_type"], "value") else data["elder_type"],
        data["mobility_level"].value if hasattr(data["mobility_level"], "value") else data["mobility_level"],
        data.get("is_living_alone", False),
        missing_count
    )
    match_priority = _calculate_match_priority(risk_level, data.get("is_living_alone", False))
    expected_window_val = data["expected_window"].value if data.get("expected_window") and hasattr(data["expected_window"], "value") else data.get("expected_window")
    matched = self._match_companions(
        community=data["community"],
        item_code=data["item_code"],
        expected_window=expected_window_val,
        risk_level=risk_level,
        expected_date=data["expected_date"]
    )
    primary = matched[0] if matched else None
    material_reminders = self._generate_material_reminders(missing_materials, data["item_code"])
    route_hints = self._generate_route_hints(data["community"], expected_window_val)
    risk_alerts = self._generate_risk_alerts(
        risk_level,
        data["mobility_level"].value if hasattr(data["mobility_level"], "value") else data["mobility_level"],
        data.get("is_living_alone", False),
        missing_count
    )
    now = datetime.now()
    appointment_no = _generate_appointment_no(now)
    status = "matched" if primary else "pending_match"
    expected_service_period = "上午 09:00-11:30"  # 默认时段
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO accompany_appointments
            (appointment_no, elder_name, elder_type, item_code, item_name, mobility_level,
             is_living_alone, accompany_demand_type, expected_date, community, contact_phone,
             special_notes, pre_review_order_id, verify_history_id, expected_window,
             status, risk_level, missing_materials_json, match_priority,
             recommended_companion_id, recommended_companion_name, recommended_companion_type,
             recommended_companion_phone, expected_service_period,
             material_reminders_json, route_hints_json, risk_alerts_json,
             confirm_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            appointment_no,
            data["elder_name"],
            data["elder_type"].value if hasattr(data["elder_type"], "value") else data["elder_type"],
            data["item_code"],
            item_name,
            data["mobility_level"].value if hasattr(data["mobility_level"], "value") else data["mobility_level"],
            1 if data.get("is_living_alone") else 0,
            data["accompany_demand_type"].value if hasattr(data["accompany_demand_type"], "value") else data["accompany_demand_type"],
            data["expected_date"],
            data["community"],
            data["contact_phone"],
            data.get("special_notes"),
            data.get("pre_review_order_id"),
            data.get("verify_history_id"),
            expected_window_val,
            status,
            risk_level,
            json.dumps(missing_materials, ensure_ascii=False),
            match_priority,
            primary.companion_id if primary else None,
            primary.companion_name if primary else None,
            primary.companion_type if primary else None,
            primary.phone if primary else None,
            expected_service_period,
            json.dumps(material_reminders, ensure_ascii=False),
            json.dumps(route_hints, ensure_ascii=False),
            json.dumps(risk_alerts, ensure_ascii=False),
            "unconfirmed",
            now.isoformat(),
            now.isoformat()
        ))
        new_id = c.lastrowid
        for m in matched:
            c.execute("""
                INSERT INTO accompany_match_candidates
                (appointment_id, companion_id, match_priority, match_score, match_reasons_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                new_id, m.companion_id, m.match_priority, m.match_score,
                json.dumps(m.match_reasons, ensure_ascii=False),
                now.isoformat()
            ))
        c.execute("""
            INSERT INTO accompany_status_history
            (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (new_id, appointment_no, None, status, "system", "预约创建并自动匹配", now.isoformat()))
    appointment = self.get_accompany_appointment(new_id)
    return {
        "appointment": appointment,
        "matched_candidates": matched
    }


Database.create_accompany_appointment = db_create_accompany_appointment


def db_get_accompany_appointment(self, appointment_id: int) -> Optional[AccompanyAppointment]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM accompany_appointments WHERE id = ?", (appointment_id,))
        row = c.fetchone()
        return _row_to_accompany_appointment(row) if row else None


Database.get_accompany_appointment = db_get_accompany_appointment


def db_get_accompany_appointment_by_no(self, appointment_no: str) -> Optional[AccompanyAppointment]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM accompany_appointments WHERE appointment_no = ?", (appointment_no,))
        row = c.fetchone()
        return _row_to_accompany_appointment(row) if row else None


Database.get_accompany_appointment_by_no = db_get_accompany_appointment_by_no


def db_get_match_candidates(self, appointment_id: int) -> List[MatchedCompanion]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT mc.*, cr.name, cr.companion_type, cr.phone, cr.community
            FROM accompany_match_candidates mc
            JOIN companion_resources cr ON mc.companion_id = cr.id
            WHERE mc.appointment_id = ?
            ORDER BY mc.match_priority ASC
        """, (appointment_id,))
        results = []
        for r in c.fetchall():
            results.append(MatchedCompanion(
                companion_id=r["companion_id"],
                companion_name=r["name"],
                companion_type=r["companion_type"],
                phone=r["phone"],
                community=r["community"],
                match_priority=r["match_priority"],
                match_score=r["match_score"],
                match_reasons=json.loads(r["match_reasons_json"]) if r["match_reasons_json"] else []
            ))
        return results


Database.get_match_candidates = db_get_match_candidates


def db_list_accompany_appointments(
    self,
    community: Optional[str] = None,
    item_code: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    expected_date: Optional[str] = None,
    recommended_companion_id: Optional[int] = None,
    risk_level: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    sql = "SELECT * FROM accompany_appointments WHERE 1=1"
    count_sql = "SELECT COUNT(*) as cnt FROM accompany_appointments WHERE 1=1"
    params = []
    if community:
        sql += " AND community = ?"
        count_sql += " AND community = ?"
        params.append(community)
    if item_code:
        sql += " AND item_code = ?"
        count_sql += " AND item_code = ?"
        params.append(item_code)
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
    if expected_date:
        sql += " AND expected_date = ?"
        count_sql += " AND expected_date = ?"
        params.append(expected_date)
    if recommended_companion_id:
        sql += " AND recommended_companion_id = ?"
        count_sql += " AND recommended_companion_id = ?"
        params.append(recommended_companion_id)
    if risk_level:
        sql += " AND risk_level = ?"
        count_sql += " AND risk_level = ?"
        params.append(risk_level)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(count_sql, params)
        total = c.fetchone()["cnt"] or 0
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size
        full_params = params + [page_size, offset]
        c.execute(sql, full_params)
        items = [_row_to_accompany_appointment(r) for r in c.fetchall()]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items
    }


Database.list_accompany_appointments = db_list_accompany_appointments


def db_reassign_appointment(
    self,
    appointment_id: int,
    new_companion_id: int,
    reassign_reason: str,
    operator: str
) -> Optional[AccompanyAppointment]:
    existing = self.get_accompany_appointment(appointment_id)
    if not existing:
        return None
    new_companion = self.get_companion_resource(new_companion_id)
    if not new_companion:
        raise ValueError(f"陪同人ID {new_companion_id} 不存在")
    if not new_companion.is_active:
        raise ValueError(f"陪同人 {new_companion.name} 已停用")
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE accompany_appointments
            SET recommended_companion_id = ?,
                recommended_companion_name = ?,
                recommended_companion_type = ?,
                recommended_companion_phone = ?,
                status = 'reassigned',
                confirm_status = 'unconfirmed',
                updated_at = ?
            WHERE id = ?
        """, (
            new_companion.id, new_companion.name, new_companion.companion_type,
            new_companion.phone, now.isoformat(), appointment_id
        ))
        c.execute("""
            INSERT INTO accompany_status_history
            (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            appointment_id, existing.appointment_no, existing.status,
            "reassigned", operator, f"改派原因：{reassign_reason}", now.isoformat()
        ))
    return self.get_accompany_appointment(appointment_id)


Database.reassign_appointment = db_reassign_appointment


def db_update_accompany_status(
    self,
    appointment_id: int,
    status: str,
    operator: Optional[str] = None,
    remark: Optional[str] = None
) -> Optional[AccompanyAppointment]:
    existing = self.get_accompany_appointment(appointment_id)
    if not existing:
        return None
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE accompany_appointments
            SET status = ?, updated_at = ?
            WHERE id = ?
        """, (status, now.isoformat(), appointment_id))
        c.execute("""
            INSERT INTO accompany_status_history
            (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            appointment_id, existing.appointment_no, existing.status,
            status, operator, remark, now.isoformat()
        ))
    return self.get_accompany_appointment(appointment_id)


Database.update_accompany_status = db_update_accompany_status


def db_cancel_appointment(
    self,
    appointment_id: int,
    cancel_reason: str,
    cancel_remark: Optional[str] = None,
    operator: Optional[str] = None
) -> Optional[AccompanyAppointment]:
    existing = self.get_accompany_appointment(appointment_id)
    if not existing:
        return None
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE accompany_appointments
            SET status = 'cancelled',
                cancel_reason = ?,
                cancel_remark = ?,
                updated_at = ?
            WHERE id = ?
        """, (cancel_reason, cancel_remark, now.isoformat(), appointment_id))
        c.execute("""
            INSERT INTO accompany_status_history
            (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            appointment_id, existing.appointment_no, existing.status,
            "cancelled", operator,
            f"取消原因：{cancel_reason}" + (f" - {cancel_remark}" if cancel_remark else ""),
            now.isoformat()
        ))
    return self.get_accompany_appointment(appointment_id)


Database.cancel_appointment = db_cancel_appointment


def db_get_appointment_status_history(self, appointment_id: int) -> List[Dict[str, Any]]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM accompany_status_history
            WHERE appointment_id = ?
            ORDER BY created_at ASC
        """, (appointment_id,))
        records = []
        for r in c.fetchall():
            records.append({
                "id": r["id"],
                "appointment_id": r["appointment_id"],
                "appointment_no": r["appointment_no"],
                "from_status": r["from_status"],
                "to_status": r["to_status"],
                "operator": r["operator"],
                "remark": r["remark"],
                "created_at": r["created_at"]
            })
        return records


Database.get_appointment_status_history = db_get_appointment_status_history


def db_create_follow_up(self, data: Dict[str, Any]) -> AccompanyFollowUpRecord:
    appointment = self.get_accompany_appointment(data["appointment_id"])
    if not appointment:
        raise ValueError(f"陪同预约ID {data['appointment_id']} 不存在")
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO accompany_follow_ups
            (appointment_id, appointment_no, is_companion_arrived, is_elder_satisfied,
             materials_completed, failed_materials_json, service_duration_minutes,
             issues_json, suggestions, follower, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["appointment_id"],
            appointment.appointment_no,
            1 if data.get("is_companion_arrived") else 0,
            1 if data.get("is_elder_satisfied") else 0,
            1 if data.get("materials_completed") else 0,
            json.dumps(data.get("failed_materials", []), ensure_ascii=False),
            data.get("service_duration_minutes", 0),
            json.dumps(data.get("issues", []), ensure_ascii=False),
            data.get("suggestions"),
            data["follower"],
            now.isoformat()
        ))
        new_id = c.lastrowid
        if data.get("is_elder_satisfied"):
            c.execute("""
                UPDATE accompany_appointments
                SET status = 'completed', updated_at = ?
                WHERE id = ?
            """, (now.isoformat(), data["appointment_id"]))
            c.execute("""
                INSERT INTO accompany_status_history
                (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data["appointment_id"], appointment.appointment_no, appointment.status,
                "completed", data["follower"], "回访完成，服务结束", now.isoformat()
            ))
        c.execute("SELECT * FROM accompany_follow_ups WHERE id = ?", (new_id,))
        return _row_to_follow_up(c.fetchone())


Database.create_follow_up = db_create_follow_up


def db_get_follow_ups_by_appointment(self, appointment_id: int) -> List[AccompanyFollowUpRecord]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM accompany_follow_ups
            WHERE appointment_id = ?
            ORDER BY created_at DESC
        """, (appointment_id,))
        return [_row_to_follow_up(r) for r in c.fetchall()]


Database.get_follow_ups_by_appointment = db_get_follow_ups_by_appointment


def db_get_accompany_stats(
    self,
    community: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    base_sql = "SELECT * FROM accompany_appointments WHERE 1=1"
    params = []
    if community:
        base_sql += " AND community = ?"
        params.append(community)
    if start_date:
        base_sql += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        base_sql += " AND date(created_at) <= date(?)"
        params.append(end_date)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as total"), params)
        total_appointments = c.fetchone()["total"] or 0
        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'completed'", params)
        completed_count = c.fetchone()["cnt"] or 0
        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'no_show'", params)
        no_show_count = c.fetchone()["cnt"] or 0
        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'cancelled'", params)
        cancelled_count = c.fetchone()["cnt"] or 0
        fu_sql = """
            SELECT AVG(fu.service_duration_minutes) as avg_dur,
                   SUM(CASE WHEN fu.is_elder_satisfied = 1 THEN 1 ELSE 0 END) as sat_cnt,
                   COUNT(fu.id) as fu_total
            FROM accompany_follow_ups fu
            JOIN accompany_appointments aa ON fu.appointment_id = aa.id
            WHERE 1=1
        """
        fu_params = []
        if community:
            fu_sql += " AND aa.community = ?"
            fu_params.append(community)
        if start_date:
            fu_sql += " AND date(aa.created_at) >= date(?)"
            fu_params.append(start_date)
        if end_date:
            fu_sql += " AND date(aa.created_at) <= date(?)"
            fu_params.append(end_date)
        c.execute(fu_sql, fu_params)
        fu_row = c.fetchone()
        avg_duration = round(fu_row["avg_dur"] or 0.0, 2)
        fu_total = fu_row["fu_total"] or 0
        sat_cnt = fu_row["sat_cnt"] or 0
        satisfaction_rate = round(sat_cnt / fu_total, 4) if fu_total > 0 else 0.0
        comm_sql = """
            SELECT aa.community,
                   COUNT(*) as total,
                   SUM(CASE WHEN aa.status = 'completed' THEN 1 ELSE 0 END) as completed_cnt,
                   SUM(CASE WHEN aa.status = 'no_show' THEN 1 ELSE 0 END) as no_show_cnt
            FROM accompany_appointments aa
            WHERE 1=1
        """
        comm_params = []
        if start_date:
            comm_sql += " AND date(aa.created_at) >= date(?)"
            comm_params.append(start_date)
        if end_date:
            comm_sql += " AND date(aa.created_at) <= date(?)"
            comm_params.append(end_date)
        comm_sql += " GROUP BY aa.community ORDER BY total DESC"
        c.execute(comm_sql, comm_params)
        community_stats = []
        for r in c.fetchall():
            total = r["total"] or 0
            cc = r["completed_cnt"] or 0
            ns = r["no_show_cnt"] or 0
            community_stats.append(AccompanyStatsCommunity(
                community=r["community"],
                total_appointments=total,
                completed_count=cc,
                completion_rate=round(cc / total, 4) if total > 0 else 0.0,
                no_show_count=ns,
                no_show_rate=round(ns / total, 4) if total > 0 else 0.0
            ))
        risk_sql = """
            SELECT aa.community,
                   COUNT(DISTINCT CASE WHEN aa.risk_level IN ('high', 'critical') THEN aa.elder_name || aa.contact_phone END) as high_risk_cnt,
                   SUM(CASE WHEN aa.risk_level IN ('high', 'critical') AND aa.status = 'completed' THEN 1 ELSE 0 END) as accompanied_cnt
            FROM accompany_appointments aa
            WHERE 1=1
        """
        risk_params = []
        if start_date:
            risk_sql += " AND date(aa.created_at) >= date(?)"
            risk_params.append(start_date)
        if end_date:
            risk_sql += " AND date(aa.created_at) <= date(?)"
            risk_params.append(end_date)
        risk_sql += " GROUP BY aa.community"
        c.execute(risk_sql, risk_params)
        risk_coverage_stats = []
        for r in c.fetchall():
            hr = r["high_risk_cnt"] or 0
            ac = r["accompanied_cnt"] or 0
            risk_coverage_stats.append(AccompanyStatsRiskCoverage(
                community=r["community"],
                high_risk_elder_count=hr,
                accompanied_count=ac,
                coverage_rate=round(ac / hr, 4) if hr > 0 else 0.0
            ))
        workload_sql = """
            SELECT aa.recommended_companion_id as cid,
                   cr.name, cr.companion_type, cr.community,
                   COUNT(*) as total_services,
                   AVG(fu.service_duration_minutes) as avg_dur
            FROM accompany_appointments aa
            JOIN companion_resources cr ON aa.recommended_companion_id = cr.id
            LEFT JOIN accompany_follow_ups fu ON aa.id = fu.appointment_id
            WHERE aa.status = 'completed'
        """
        wl_params = []
        if community:
            workload_sql += " AND aa.community = ?"
            wl_params.append(community)
        if start_date:
            workload_sql += " AND date(aa.created_at) >= date(?)"
            wl_params.append(start_date)
        if end_date:
            workload_sql += " AND date(aa.created_at) <= date(?)"
            wl_params.append(end_date)
        workload_sql += " GROUP BY aa.recommended_companion_id ORDER BY total_services DESC LIMIT 20"
        c.execute(workload_sql, wl_params)
        companion_workload_ranking = []
        for r in c.fetchall():
            companion_workload_ranking.append(AccompanyStatsCompanionWorkload(
                companion_id=r["cid"],
                companion_name=r["name"],
                companion_type=r["companion_type"],
                community=r["community"],
                total_services=r["total_services"] or 0,
                avg_duration_minutes=round(r["avg_dur"] or 0.0, 2)
            ))
        mat_sql = """
            SELECT value as mat_name, COUNT(*) as fail_cnt
            FROM accompany_follow_ups,
                 json_each(accompany_follow_ups.failed_materials_json)
            WHERE accompany_follow_ups.materials_completed = 0
        """
        mat_params = []
        if start_date or end_date:
            mat_sql += " AND accompany_follow_ups.appointment_id IN (SELECT id FROM accompany_appointments WHERE 1=1"
            if start_date:
                mat_sql += " AND date(created_at) >= date(?)"
                mat_params.append(start_date)
            if end_date:
                mat_sql += " AND date(created_at) <= date(?)"
                mat_params.append(end_date)
            mat_sql += ")"
        mat_sql += " GROUP BY value ORDER BY fail_cnt DESC LIMIT 20"
        c.execute(mat_sql, mat_params)
        material_failure_ranking = []
        rank = 0
        for r in c.fetchall():
            rank += 1
            material_failure_ranking.append(AccompanyStatsMaterialFailure(
                material_name=r["mat_name"],
                failure_count=r["fail_cnt"] or 0,
                rank=rank
            ))
    overall = AccompanyStatsOverall(
        total_appointments=total_appointments,
        completed_count=completed_count,
        completion_rate=round(completed_count / total_appointments, 4) if total_appointments > 0 else 0.0,
        no_show_count=no_show_count,
        no_show_rate=round(no_show_count / total_appointments, 4) if total_appointments > 0 else 0.0,
        cancelled_count=cancelled_count,
        avg_service_duration_minutes=avg_duration,
        satisfaction_rate=satisfaction_rate,
        community_stats=community_stats,
        risk_coverage_stats=risk_coverage_stats,
        companion_workload_ranking=companion_workload_ranking,
        material_failure_ranking=material_failure_ranking
    )
    return overall.model_dump(mode="json")


Database.get_accompany_stats = db_get_accompany_stats


def _row_to_exception_order(row: sqlite3.Row) -> ExceptionDisposalOrder:
    return ExceptionDisposalOrder(
        id=row["id"],
        exception_no=row["exception_no"],
        exception_type=row["exception_type"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        elder_name=row["elder_name"],
        elder_type=row["elder_type"],
        community=row["community"],
        expected_window=row["expected_window"],
        reporter=row["reporter"],
        reporter_role=row["reporter_role"],
        reporter_phone=row["reporter_phone"],
        description=row["description"],
        location=row["location"],
        impact_completion=bool(row["impact_completion"]),
        risk_level=row["risk_level"],
        status=row["status"],
        priority=row["priority"],
        responsible_role=row["responsible_role"],
        responsible_person=row["responsible_person"],
        responsible_phone=row["responsible_phone"],
        suggested_actions=json.loads(row["suggested_actions_json"]) if row["suggested_actions_json"] else [],
        latest_deadline=datetime.fromisoformat(row["latest_deadline"]),
        follow_up_required=bool(row["follow_up_required"]),
        follow_up_deadline=datetime.fromisoformat(row["follow_up_deadline"]) if row["follow_up_deadline"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
        closed_by=row["closed_by"],
        close_remark=row["close_remark"]
    )


def _row_to_processing_record(row: sqlite3.Row) -> ExceptionProcessingRecord:
    return ExceptionProcessingRecord(
        id=row["id"],
        exception_id=row["exception_id"],
        processor=row["processor"],
        action=row["action"],
        result=row["result"],
        next_step=row["next_step"],
        duration_minutes=row["duration_minutes"] or 0,
        created_at=datetime.fromisoformat(row["created_at"])
    )


def _row_to_status_history(row: sqlite3.Row) -> ExceptionStatusHistory:
    return ExceptionStatusHistory(
        id=row["id"],
        exception_id=row["exception_id"],
        from_status=row["from_status"],
        to_status=row["to_status"],
        operator=row["operator"],
        remark=row["remark"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


def _generate_exception_no(dt: datetime) -> str:
    return f"EX{dt.strftime('%Y%m%d%H%M%S')}{dt.microsecond // 1000:03d}"


EXCEPTION_TYPE_NAMES = {
    "window_reject": "窗口退回",
    "material_invalid": "材料被判无效",
    "elder_absent": "老人未到场",
    "companion_late": "陪同人迟到",
    "supplement_fail": "现场补件失败",
    "policy_changed": "窗口政策变更",
    "elder_unwell": "老人身体不适",
    "other": "其他异常"
}


def _generate_disposal_plan(
    exception_type: str,
    elder_type: Optional[str],
    risk_level: Optional[str],
    impact_completion: bool,
    item_code: Optional[str]
) -> Dict[str, Any]:
    from datetime import timedelta
    now = datetime.now()

    urgent_types = ["elder_unwell", "elder_absent"]
    high_types = ["window_reject", "material_invalid", "policy_changed", "companion_late"]
    medium_types = ["supplement_fail"]

    if exception_type in urgent_types:
        base_priority = "p1_urgent"
    elif exception_type in high_types:
        base_priority = "p2_high"
    elif exception_type in medium_types:
        base_priority = "p3_medium"
    else:
        base_priority = "p4_low"

    priority_levels = {
        "p1_urgent": 4,
        "p2_high": 3,
        "p3_medium": 2,
        "p4_low": 1
    }
    current_level = priority_levels[base_priority]

    if risk_level == "critical":
        current_level = min(current_level + 2, 4)
    elif risk_level == "high":
        current_level = min(current_level + 1, 4)

    if elder_type in ("special_elder", "disabled", "low_income"):
        current_level = min(current_level + 1, 4)

    if impact_completion:
        current_level = min(current_level + 1, 4)

    level_to_priority = {v: k for k, v in priority_levels.items()}
    priority = level_to_priority[current_level]

    deadline_hours = {
        "p1_urgent": 1,
        "p2_high": 4,
        "p3_medium": 24,
        "p4_low": 72
    }
    latest_deadline = now + timedelta(hours=deadline_hours.get(priority, 24))
    follow_up_deadline = now + timedelta(days=3)

    type_role_map = {
        "window_reject": ResponsibleRole.WINDOW_STAFF.value,
        "material_invalid": ResponsibleRole.WINDOW_STAFF.value,
        "elder_absent": ResponsibleRole.COMMUNITY_WORKER.value,
        "companion_late": ResponsibleRole.ACCOMPANY_MANAGER.value,
        "supplement_fail": ResponsibleRole.WINDOW_STAFF.value,
        "policy_changed": ResponsibleRole.SUPERVISOR.value,
        "elder_unwell": ResponsibleRole.MEDICAL_STAFF.value,
        "other": ResponsibleRole.SUPERVISOR.value
    }
    responsible_role = type_role_map.get(exception_type, ResponsibleRole.SUPERVISOR.value)

    type_actions_map = {
        "window_reject": [
            "立即核实退回原因，与窗口确认最新政策要求",
            "联系老人或家属说明情况，解释退回复核要点",
            "协助重新准备缺失或不符合要求的材料",
            "安排二次预审或预约下次办理时间"
        ],
        "material_invalid": [
            "确认材料无效的具体原因（过期、复印不清、信息不符等）",
            "告知家属需要重新准备的材料清单和规范",
            "协调社区或相关部门出具证明材料",
            "跟踪材料重新准备进度"
        ],
        "elder_absent": [
            "联系家属确认老人未到场原因",
            "如为身体原因，协调上门服务或改期办理",
            "评估是否需要安排陪同服务",
            "记录老人情况并持续关注"
        ],
        "companion_late": [
            "联系陪同人确认位置和预计到达时间",
            "如陪同人无法按时到达，协调备用陪同人",
            "与窗口沟通延迟取号或改期",
            "事后评估陪同资源调度机制"
        ],
        "supplement_fail": [
            "分析补件失败的具体环节和原因",
            "与材料出具部门协调加急处理",
            "安排专人协助办理补充材料",
            "视情况启动容缺受理或绿色通道"
        ],
        "policy_changed": [
            "获取窗口最新政策文件和执行标准",
            "更新系统事项配置和材料清单",
            "通知近期预约老人政策变动情况",
            "开展窗口人员培训确保政策统一执行"
        ],
        "elder_unwell": [
            "立即联系医护人员或拨打急救电话",
            "安抚老人情绪并提供临时休息场所",
            "通知家属老人情况",
            "评估老人身体状况，改期或安排上门办理"
        ],
        "other": [
            "调查核实异常具体情况",
            "协调相关责任部门处理",
            "保持与老人和家属的沟通",
            "记录异常原因形成案例库"
        ]
    }
    suggested_actions = type_actions_map.get(exception_type, type_actions_map["other"])

    if impact_completion:
        suggested_actions.append("【重要】该异常已影响事项办理进度，需优先处理并跟踪至完成")

    if risk_level in ("high", "critical"):
        suggested_actions.append("【风险提示】涉及高风险老人，处置过程需特别关注老人安全与感受")

    follow_up_required = True
    if exception_type in ("other",) and not impact_completion and risk_level in ("low", "medium"):
        follow_up_required = False

    return {
        "priority": priority,
        "responsible_role": responsible_role,
        "suggested_actions": suggested_actions,
        "latest_deadline": latest_deadline,
        "follow_up_required": follow_up_required,
        "follow_up_deadline": follow_up_deadline if follow_up_required else None
    }


def _fetch_source_info(self, source_type: str, source_id: int) -> Optional[Dict[str, Any]]:
    if source_type == "verify_record":
        return self.get_history_detail(source_id)
    elif source_type == "pre_review_order":
        order = self.get_pre_review_order(source_id)
        return order.model_dump(mode="json") if order else None
    elif source_type == "accompany_appointment":
        appt = self.get_accompany_appointment(source_id)
        return appt.model_dump(mode="json") if appt else None
    return None


Database._fetch_source_info = _fetch_source_info


def _check_source_exists(self, source_type: str, source_id: int) -> bool:
    with self._connect() as conn:
        c = conn.cursor()
        if source_type == "verify_record":
            c.execute("SELECT id FROM verification_history WHERE id = ?", (source_id,))
        elif source_type == "pre_review_order":
            c.execute("SELECT id FROM pre_review_orders WHERE id = ?", (source_id,))
        elif source_type == "accompany_appointment":
            c.execute("SELECT id FROM accompany_appointments WHERE id = ?", (source_id,))
        else:
            return False
        return c.fetchone() is not None


Database.check_source_exists = _check_source_exists


def db_create_exception(self, data: Dict[str, Any]) -> ExceptionDisposalOrder:
    source_type = data["source_type"].value if hasattr(data["source_type"], "value") else data["source_type"]
    source_id = data["source_id"]

    if not self.check_source_exists(source_type, source_id):
        type_names = {
            "verify_record": "材料校验记录",
            "pre_review_order": "预审工单",
            "accompany_appointment": "陪同预约单"
        }
        type_name = type_names.get(source_type, source_type)
        raise ValueError(f"关联的{type_name}(ID={source_id})不存在")

    item_code = None
    item_name = None
    elder_name = None
    elder_type = None
    community = None
    expected_window = None

    source_info = self._fetch_source_info(source_type, source_id)
    if source_info:
        if source_type == "verify_record":
            record = source_info.get("record")
            if record:
                if hasattr(record, "item_code"):
                    item_code = record.item_code
                    item_name = record.item_name
                    elder_type = record.elder_type
                else:
                    item_code = record.get("item_code")
                    item_name = record.get("item_name")
                    elder_type = record.get("elder_type")
        elif source_type == "pre_review_order":
            item_code = source_info.get("item_code")
            item_name = source_info.get("item_name")
            elder_name = source_info.get("elder_name")
            elder_type = source_info.get("elder_type")
            expected_window = source_info.get("expected_window")
        elif source_type == "accompany_appointment":
            item_code = source_info.get("item_code")
            item_name = source_info.get("item_name")
            elder_name = source_info.get("elder_name")
            elder_type = source_info.get("elder_type")
            community = source_info.get("community")
            expected_window = source_info.get("expected_window")

    if elder_type in ("special_elder", "disabled", "low_income"):
        derived_risk = "high"
    elif elder_type == "remote_resident":
        derived_risk = "medium"
    else:
        derived_risk = "medium"

    exception_type_val = data["exception_type"].value if hasattr(data["exception_type"], "value") else data["exception_type"]

    disposal_plan = _generate_disposal_plan(
        exception_type=exception_type_val,
        elder_type=elder_type,
        risk_level=derived_risk,
        impact_completion=data.get("impact_completion", True),
        item_code=item_code
    )

    now = datetime.now()
    exception_no = _generate_exception_no(now)

    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO exception_disposal_orders
            (exception_no, exception_type, source_type, source_id,
             item_code, item_name, elder_name, elder_type, community, expected_window,
             reporter, reporter_role, reporter_phone, description, location,
             impact_completion, risk_level, status, priority, responsible_role,
             suggested_actions_json, latest_deadline, follow_up_required, follow_up_deadline,
             evidence_images_json, extra_info_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exception_no, exception_type_val, source_type, source_id,
            item_code, item_name, elder_name, elder_type, community, expected_window,
            data["reporter"], data["reporter_role"], data.get("reporter_phone"),
            data["description"], data.get("location"),
            1 if data.get("impact_completion", True) else 0,
            derived_risk, "pending", disposal_plan["priority"],
            disposal_plan["responsible_role"],
            json.dumps(disposal_plan["suggested_actions"], ensure_ascii=False),
            disposal_plan["latest_deadline"].isoformat(),
            1 if disposal_plan["follow_up_required"] else 0,
            disposal_plan["follow_up_deadline"].isoformat() if disposal_plan["follow_up_deadline"] else None,
            json.dumps(data.get("evidence_images", []), ensure_ascii=False),
            json.dumps(data.get("extra_info", {}) or {}, ensure_ascii=False),
            now.isoformat(), now.isoformat()
        ))
        new_id = c.lastrowid
        c.execute("""
            INSERT INTO exception_status_history
            (exception_id, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (new_id, None, "pending", "system", f"异常事件自动创建并生成处置单，优先级：{disposal_plan['priority']}", now.isoformat()))

    return self.get_exception(new_id)


Database.create_exception = db_create_exception


def db_get_exception(self, exception_id: int) -> Optional[ExceptionDisposalOrder]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM exception_disposal_orders WHERE id = ?", (exception_id,))
        row = c.fetchone()
        return _row_to_exception_order(row) if row else None


Database.get_exception = db_get_exception


def db_get_exception_by_no(self, exception_no: str) -> Optional[ExceptionDisposalOrder]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM exception_disposal_orders WHERE exception_no = ?", (exception_no,))
        row = c.fetchone()
        return _row_to_exception_order(row) if row else None


Database.get_exception_by_no = db_get_exception_by_no


def db_list_exceptions(
    self,
    item_code: Optional[str] = None,
    community: Optional[str] = None,
    expected_window: Optional[str] = None,
    exception_type: Optional[str] = None,
    responsible_person: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    elder_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    sql = "SELECT * FROM exception_disposal_orders WHERE 1=1"
    count_sql = "SELECT COUNT(*) as cnt FROM exception_disposal_orders WHERE 1=1"
    params = []
    if item_code:
        sql += " AND item_code = ?"
        count_sql += " AND item_code = ?"
        params.append(item_code)
    if community:
        sql += " AND community = ?"
        count_sql += " AND community = ?"
        params.append(community)
    if expected_window:
        sql += " AND expected_window = ?"
        count_sql += " AND expected_window = ?"
        params.append(expected_window)
    if exception_type:
        sql += " AND exception_type = ?"
        count_sql += " AND exception_type = ?"
        params.append(exception_type)
    if responsible_person:
        sql += " AND responsible_person = ?"
        count_sql += " AND responsible_person = ?"
        params.append(responsible_person)
    if status:
        sql += " AND status = ?"
        count_sql += " AND status = ?"
        params.append(status)
    if priority:
        sql += " AND priority = ?"
        count_sql += " AND priority = ?"
        params.append(priority)
    if start_date:
        sql += " AND date(created_at) >= date(?)"
        count_sql += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        sql += " AND date(created_at) <= date(?)"
        count_sql += " AND date(created_at) <= date(?)"
        params.append(end_date)
    if elder_name:
        sql += " AND elder_name LIKE ?"
        count_sql += " AND elder_name LIKE ?"
        params.append(f"%{elder_name}%")
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(count_sql, params)
        total = c.fetchone()["cnt"] or 0
        sql += " ORDER BY CASE priority " \
               "WHEN 'p1_urgent' THEN 1 " \
               "WHEN 'p2_high' THEN 2 " \
               "WHEN 'p3_medium' THEN 3 " \
               "WHEN 'p4_low' THEN 4 END, " \
               "created_at DESC LIMIT ? OFFSET ?"
        offset = (page - 1) * page_size
        full_params = params + [page_size, offset]
        c.execute(sql, full_params)
        items = [_row_to_exception_order(r) for r in c.fetchall()]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items
    }


Database.list_exceptions = db_list_exceptions


def db_update_exception_status(
    self,
    exception_id: int,
    status: str,
    operator: str,
    remark: Optional[str] = None
) -> Optional[ExceptionDisposalOrder]:
    existing = self.get_exception(exception_id)
    if not existing:
        return None
    if existing.status == "closed":
        raise ValueError("已关闭的异常单不允许状态变更")
    if status == "pending" and existing.status != "pending":
        raise ValueError("不能将已进入处置流程的异常单改回待处理状态")
    from_status = existing.status
    now = datetime.now()
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE exception_disposal_orders SET status = ?, updated_at = ? WHERE id = ?
        """, (status, now.isoformat(), exception_id))
        c.execute("""
            INSERT INTO exception_status_history
            (exception_id, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (exception_id, from_status, status, operator, remark or f"状态变更为{status}", now.isoformat()))
    return self.get_exception(exception_id)


Database.update_exception_status = db_update_exception_status


def db_assign_exception(
    self,
    exception_id: int,
    responsible_role: Optional[str],
    responsible_person: str,
    responsible_phone: Optional[str],
    assigned_by: str,
    assign_remark: Optional[str] = None
) -> Optional[ExceptionDisposalOrder]:
    existing = self.get_exception(exception_id)
    if not existing:
        return None
    if existing.status == "closed":
        raise ValueError("已关闭的异常单不允许指派责任人")
    now = datetime.now()
    updates = [
        "responsible_person = ?",
        "status = 'assigned'",
        "updated_at = ?"
    ]
    params = [responsible_person, now.isoformat()]
    if responsible_role:
        updates.append("responsible_role = ?")
        params.append(responsible_role)
    if responsible_phone:
        updates.append("responsible_phone = ?")
        params.append(responsible_phone)
    params.append(exception_id)
    with self._connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE exception_disposal_orders SET {', '.join(updates)} WHERE id = ?", params)
        c.execute("""
            INSERT INTO exception_status_history
            (exception_id, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            exception_id, existing.status, "assigned", assigned_by,
            f"指派责任人：{responsible_person}" + (f"，备注：{assign_remark}" if assign_remark else ""),
            now.isoformat()
        ))
    return self.get_exception(exception_id)


Database.assign_exception = db_assign_exception


def db_add_processing_record(
    self,
    exception_id: int,
    processor: str,
    action: str,
    result: str,
    next_step: Optional[str] = None,
    duration_minutes: int = 0
) -> Optional[ExceptionProcessingRecord]:
    existing = self.get_exception(exception_id)
    if not existing:
        return None
    if existing.status == "closed":
        raise ValueError("已关闭的异常单不允许追加处理记录")
    now = datetime.now()
    new_id = None
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO exception_processing_records
            (exception_id, processor, action, result, next_step, duration_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (exception_id, processor, action, result, next_step, duration_minutes, now.isoformat()))
        new_id = c.lastrowid
        if existing.status in ("pending", "assigned"):
            c.execute("""
                UPDATE exception_disposal_orders SET status = 'in_progress', updated_at = ? WHERE id = ?
            """, (now.isoformat(), exception_id))
            c.execute("""
                INSERT INTO exception_status_history
                (exception_id, from_status, to_status, operator, remark, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (exception_id, existing.status, "in_progress", processor, "开始处理异常，记录处理动作", now.isoformat()))
    if new_id:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM exception_processing_records WHERE id = ?", (new_id,))
            return _row_to_processing_record(c.fetchone())
    return None


Database.add_processing_record = db_add_processing_record


def db_close_exception(
    self,
    exception_id: int,
    closed_by: str,
    close_remark: str,
    is_resolved: bool = True,
    follow_up_suggestion: Optional[str] = None
) -> Optional[ExceptionDisposalOrder]:
    existing = self.get_exception(exception_id)
    if not existing:
        return None
    now = datetime.now()
    status = "closed"
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE exception_disposal_orders
            SET status = ?, closed_at = ?, closed_by = ?, close_remark = ?, updated_at = ?
            WHERE id = ?
        """, (status, now.isoformat(), closed_by, close_remark, now.isoformat(), exception_id))
        remark = f"关闭异常，结果：{'已解决' if is_resolved else '未解决'}，说明：{close_remark}"
        if follow_up_suggestion:
            remark += f"，回访建议：{follow_up_suggestion}"
        c.execute("""
            INSERT INTO exception_status_history
            (exception_id, from_status, to_status, operator, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (exception_id, existing.status, status, closed_by, remark, now.isoformat()))
    return self.get_exception(exception_id)


Database.close_exception = db_close_exception


def db_get_exception_processing_records(self, exception_id: int) -> List[ExceptionProcessingRecord]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM exception_processing_records
            WHERE exception_id = ? ORDER BY created_at DESC
        """, (exception_id,))
        return [_row_to_processing_record(r) for r in c.fetchall()]


Database.get_exception_processing_records = db_get_exception_processing_records


def db_get_exception_status_history(self, exception_id: int) -> List[ExceptionStatusHistory]:
    with self._connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM exception_status_history
            WHERE exception_id = ? ORDER BY created_at ASC
        """, (exception_id,))
        return [_row_to_status_history(r) for r in c.fetchall()]


Database.get_exception_status_history = db_get_exception_status_history


def db_get_exception_stats(
    self,
    item_code: Optional[str] = None,
    community: Optional[str] = None,
    expected_window: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    base_sql = "SELECT * FROM exception_disposal_orders WHERE 1=1"
    params = []
    if item_code:
        base_sql += " AND item_code = ?"
        params.append(item_code)
    if community:
        base_sql += " AND community = ?"
        params.append(community)
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

        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as total"), params)
        total_exceptions = c.fetchone()["total"] or 0

        for status_val in ("pending", "in_progress", "resolved", "closed"):
            cnt_sql = base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + f" AND status = '{status_val}'"
            c.execute(cnt_sql, params)

        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'pending'", params)
        pending_count = c.fetchone()["cnt"] or 0

        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'in_progress'", params)
        in_progress_count = c.fetchone()["cnt"] or 0

        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'resolved'", params)
        resolved_count = c.fetchone()["cnt"] or 0

        c.execute(base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND status = 'closed'", params)
        closed_count = c.fetchone()["cnt"] or 0

        now_iso = datetime.now().isoformat()
        timeout_sql = base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND latest_deadline < ? AND status NOT IN ('closed', 'resolved')"
        timeout_params = params + [now_iso]
        c.execute(timeout_sql, timeout_params)
        timeout_count = c.fetchone()["cnt"] or 0
        timeout_rate = round(timeout_count / total_exceptions, 4) if total_exceptions > 0 else 0.0

        verify_sql = "SELECT COUNT(*) as cnt FROM verification_history"
        pr_sql = "SELECT COUNT(*) as cnt FROM pre_review_orders"
        acc_sql = "SELECT COUNT(*) as cnt FROM accompany_appointments"
        v_params = []
        p_params = []
        a_params = []
        if start_date:
            verify_sql += " WHERE date(created_at) >= date(?)"
            pr_sql += " WHERE date(created_at) >= date(?)"
            acc_sql += " WHERE date(created_at) >= date(?)"
            v_params.append(start_date)
            p_params.append(start_date)
            a_params.append(start_date)
            if end_date:
                verify_sql += " AND date(created_at) <= date(?)"
                pr_sql += " AND date(created_at) <= date(?)"
                acc_sql += " AND date(created_at) <= date(?)"
                v_params.append(end_date)
                p_params.append(end_date)
                a_params.append(end_date)
        elif end_date:
            verify_sql += " WHERE date(created_at) <= date(?)"
            pr_sql += " WHERE date(created_at) <= date(?)"
            acc_sql += " WHERE date(created_at) <= date(?)"
            v_params.append(end_date)
            p_params.append(end_date)
            a_params.append(end_date)

        c.execute(verify_sql, v_params)
        total_verify = c.fetchone()["cnt"] or 0
        c.execute(pr_sql, p_params)
        total_pr = c.fetchone()["cnt"] or 0
        c.execute(acc_sql, a_params)
        total_acc_for_rate = c.fetchone()["cnt"] or 0
        total_transactions = total_verify + total_pr + total_acc_for_rate
        raw_rate = (total_exceptions / total_transactions) if total_transactions > 0 else 0.0
        exception_rate = round(min(raw_rate, 1.0), 4)

        item_rank_sql = """
            SELECT si.item_code, si.item_name,
                   COUNT(eo.id) as exc_cnt
            FROM service_items si
            LEFT JOIN exception_disposal_orders eo ON si.item_code = eo.item_code
            WHERE 1=1
        """
        ir_params = []
        if community:
            item_rank_sql += " AND eo.community = ?"
            ir_params.append(community)
        if expected_window:
            item_rank_sql += " AND eo.expected_window = ?"
            ir_params.append(expected_window)
        if start_date:
            item_rank_sql += " AND date(eo.created_at) >= date(?)"
            ir_params.append(start_date)
        if end_date:
            item_rank_sql += " AND date(eo.created_at) <= date(?)"
            ir_params.append(end_date)
        item_rank_sql += " GROUP BY si.item_code ORDER BY exc_cnt DESC LIMIT 20"
        c.execute(item_rank_sql, ir_params)
        item_exception_ranking = []
        rank = 0
        for r in c.fetchall():
            rank += 1
            exc_cnt = r["exc_cnt"] or 0
            item_total_sql = "SELECT COUNT(*) as cnt FROM (" \
                             "SELECT id FROM verification_history WHERE item_code = ? " \
                             "UNION ALL SELECT id FROM pre_review_orders WHERE item_code = ? " \
                             "UNION ALL SELECT id FROM accompany_appointments WHERE item_code = ?" \
                             ") t"
            t_params = [r["item_code"], r["item_code"], r["item_code"]]
            if start_date or end_date:
                item_total_sql = "SELECT COUNT(*) as cnt FROM (" \
                                 "SELECT id FROM verification_history WHERE item_code = ? {date_clause_v}" \
                                 " UNION ALL SELECT id FROM pre_review_orders WHERE item_code = ? {date_clause_pr}" \
                                 " UNION ALL SELECT id FROM accompany_appointments WHERE item_code = ? {date_clause_acc}" \
                                 ") t"
                date_clause_v = ""
                date_clause_pr = ""
                date_clause_acc = ""
                extra_params = []
                if start_date:
                    date_clause_v += " AND date(created_at) >= date(?)"
                    date_clause_pr += " AND date(created_at) >= date(?)"
                    date_clause_acc += " AND date(created_at) >= date(?)"
                    extra_params.extend([start_date, start_date, start_date])
                if end_date:
                    date_clause_v += " AND date(created_at) <= date(?)"
                    date_clause_pr += " AND date(created_at) <= date(?)"
                    date_clause_acc += " AND date(created_at) <= date(?)"
                    extra_params.extend([end_date, end_date, end_date])
                item_total_sql = item_total_sql.format(
                    date_clause_v=date_clause_v,
                    date_clause_pr=date_clause_pr,
                    date_clause_acc=date_clause_acc
                )
                t_params.extend(extra_params)
            c.execute(item_total_sql, t_params)
            item_total = c.fetchone()["cnt"] or 0
            raw_item_rate = (exc_cnt / item_total) if item_total > 0 else 0.0
            item_exception_ranking.append(ExceptionStatsItemRank(
                item_code=r["item_code"],
                item_name=r["item_name"],
                exception_count=exc_cnt,
                exception_rate=round(min(raw_item_rate, 1.0), 4),
                rank=rank
            ))

        type_duration_sql = """
            SELECT exception_type,
                   COUNT(*) as cnt,
                   AVG((julianday(COALESCE(closed_at, ?)) - julianday(created_at)) * 1440) as avg_dur
            FROM exception_disposal_orders
            WHERE 1=1
        """
        td_params = [now_iso]
        if item_code:
            type_duration_sql += " AND item_code = ?"
            td_params.append(item_code)
        if community:
            type_duration_sql += " AND community = ?"
            td_params.append(community)
        if expected_window:
            type_duration_sql += " AND expected_window = ?"
            td_params.append(expected_window)
        if start_date:
            type_duration_sql += " AND date(created_at) >= date(?)"
            td_params.append(start_date)
        if end_date:
            type_duration_sql += " AND date(created_at) <= date(?)"
            td_params.append(end_date)
        type_duration_sql += " GROUP BY exception_type ORDER BY cnt DESC"
        c.execute(type_duration_sql, td_params)
        type_avg_duration = []
        for r in c.fetchall():
            type_avg_duration.append(ExceptionStatsTypeAvgDuration(
                exception_type=r["exception_type"],
                exception_type_name=EXCEPTION_TYPE_NAMES.get(r["exception_type"], r["exception_type"]),
                avg_duration_minutes=round(r["avg_dur"] or 0.0, 2),
                count=r["cnt"] or 0
            ))

        failure_sql = """
            SELECT eo.exception_type, COUNT(*) as cnt
            FROM exception_disposal_orders eo
            WHERE eo.impact_completion = 1
        """
        f_params = []
        if item_code:
            failure_sql += " AND eo.item_code = ?"
            f_params.append(item_code)
        if community:
            failure_sql += " AND eo.community = ?"
            f_params.append(community)
        if expected_window:
            failure_sql += " AND eo.expected_window = ?"
            f_params.append(expected_window)
        if start_date:
            failure_sql += " AND date(eo.created_at) >= date(?)"
            f_params.append(start_date)
        if end_date:
            failure_sql += " AND date(eo.created_at) <= date(?)"
            f_params.append(end_date)
        failure_sql += " GROUP BY eo.exception_type ORDER BY cnt DESC LIMIT 10"
        c.execute(failure_sql, f_params)
        top_failure_reasons = []
        rank = 0
        for r in c.fetchall():
            rank += 1
            top_failure_reasons.append(ExceptionStatsFailureReason(
                reason=EXCEPTION_TYPE_NAMES.get(r["exception_type"], r["exception_type"]),
                count=r["cnt"] or 0,
                rank=rank
            ))

        acc_exc_sql = base_sql.replace("SELECT *", "SELECT COUNT(*) as cnt") + " AND source_type = 'accompany_appointment'"
        c.execute(acc_exc_sql, params)
        accompany_exception_count = c.fetchone()["cnt"] or 0

        c.execute(acc_sql, a_params)
        accompany_total = c.fetchone()["cnt"] or 0
        raw_acc_rate = (accompany_exception_count / accompany_total) if accompany_total > 0 else 0.0
        accompany_exception_rate = round(min(raw_acc_rate, 1.0), 4)

        raw_timeout_rate = (timeout_count / total_exceptions) if total_exceptions > 0 else 0.0
        timeout_rate = round(min(raw_timeout_rate, 1.0), 4)

    overall = ExceptionStatsOverall(
        total_exceptions=total_exceptions,
        exception_rate=exception_rate,
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        resolved_count=resolved_count,
        closed_count=closed_count,
        timeout_count=timeout_count,
        timeout_rate=timeout_rate,
        item_exception_ranking=item_exception_ranking,
        type_avg_duration=type_avg_duration,
        top_failure_reasons=top_failure_reasons,
        accompany_exception_rate=accompany_exception_rate,
        accompany_exception_count=accompany_exception_count,
        accompany_total=accompany_total
    )
    return overall.model_dump(mode="json")


Database.get_exception_stats = db_get_exception_stats
