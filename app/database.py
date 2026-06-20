import sqlite3
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager

from .schemas import ServiceItemCreate
from .db_utils import DictEncoder, json_dumps, json_loads, bool_to_int, now_iso
from .repositories.verify_repo import VerifyRepository
from .repositories.pre_review_repo import PreReviewRepository
from .repositories.accompany_repo import AccompanyRepository
from .repositories.exception_repo import ExceptionRepository
from .repositories.policy_repo import PolicyRepository
from .repositories.stats_repo import StatsRepository
from .services.exception_service import create_exception as svc_create_exception
from .services.accompany_service import (
    create_accompany_appointment as svc_create_accompany_appointment,
    _match_companions as svc_match_companions,
    _generate_material_reminders as svc_generate_material_reminders,
    _generate_route_hints as svc_generate_route_hints,
    _generate_risk_alerts as svc_generate_risk_alerts,
)
from .services.policy_service import (
    scan_policy_impact as svc_scan_policy_impact,
    query_policy_impact as svc_query_policy_impact,
    get_policy_change_detail as svc_get_policy_change_detail,
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "elder_service.db")


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self.verify_repo = VerifyRepository(db_path)
        self.pre_review_repo = PreReviewRepository(db_path)
        self.accompany_repo = AccompanyRepository(db_path)
        self.exception_repo = ExceptionRepository(db_path)
        self.policy_repo = PolicyRepository(db_path)
        self.stats_repo = StatsRepository(db_path)

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
            c.execute("""
                CREATE TABLE IF NOT EXISTS policy_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    applicable_items_json TEXT DEFAULT '[]',
                    applicable_windows_json TEXT DEFAULT '[]',
                    impacted_materials_json TEXT DEFAULT '[]',
                    impacted_elder_types_json TEXT DEFAULT '[]',
                    effective_date TEXT NOT NULL,
                    expiry_date TEXT,
                    policy_source TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    handling_suggestion TEXT DEFAULT '',
                    impact_types_json TEXT DEFAULT '[]',
                    description TEXT DEFAULT '',
                    added_materials_json TEXT DEFAULT '[]',
                    removed_materials_json TEXT DEFAULT '[]',
                    rejection_reasons_json TEXT DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_status ON policy_changes(status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_risk ON policy_changes(risk_level)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_effective ON policy_changes(effective_date)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS policy_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_change_id INTEGER NOT NULL,
                    policy_title TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    source_no TEXT,
                    item_code TEXT,
                    item_name TEXT,
                    elder_name TEXT,
                    elder_type TEXT,
                    community TEXT,
                    expected_window TEXT,
                    appointment_date TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'unconfirmed',
                    impact_details_json TEXT DEFAULT '[]',
                    confirmed_at TEXT,
                    confirmed_by TEXT,
                    confirm_remark TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(policy_change_id) REFERENCES policy_changes(id)
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_policy_id ON policy_warnings(policy_change_id)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_status ON policy_warnings(status)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_source ON policy_warnings(source_type, source_id)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_item ON policy_warnings(item_code)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_risk ON policy_warnings(risk_level)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_community ON policy_warnings(community)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_pw_window ON policy_warnings(expected_window)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS policy_warning_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    warning_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    remark TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(warning_id) REFERENCES policy_warnings(id)
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

    def list_items(self, enabled_only: bool = False):
        return self.verify_repo.list_items(enabled_only=enabled_only)

    def get_item(self, item_code: str):
        return self.verify_repo.get_item(item_code)

    def create_item(self, data):
        return self.verify_repo.create_item(data)

    def update_item(self, item_code: str, data):
        return self.verify_repo.update_item(item_code, data)

    def delete_item(self, item_code: str) -> bool:
        return self.verify_repo.delete_item(item_code)

    def save_verification(self, item_code, item_name, elder_type, is_agent, agent_relation, is_pass, missing_count, missing_categories, missing_details) -> int:
        return self.verify_repo.save_verification(item_code, item_name, elder_type, is_agent, agent_relation, is_pass, missing_count, missing_categories, missing_details)

    def record_make_up_attempt(self, verification_id, item_code, attempt_no, missing_before, missing_after):
        return self.verify_repo.record_make_up_attempt(verification_id, item_code, attempt_no, missing_before, missing_after)

    def list_history(self, item_code=None, is_pass=None, is_agent=None, start_date=None, end_date=None, limit=100, offset=0):
        return self.verify_repo.list_history(item_code=item_code, is_pass=is_pass, is_agent=is_agent, start_date=start_date, end_date=end_date, limit=limit, offset=offset)

    def get_history_detail(self, history_id: int):
        return self.verify_repo.get_history_detail(history_id)

    def create_pre_review_order(self, **kwargs):
        return self.pre_review_repo.create_pre_review_order(**kwargs)

    def get_pre_review_order(self, order_id: int):
        return self.pre_review_repo.get_pre_review_order(order_id)

    def get_pre_review_by_no(self, work_order_no: str):
        return self.pre_review_repo.get_pre_review_by_no(work_order_no)

    def list_pre_review_orders(self, **kwargs):
        return self.pre_review_repo.list_pre_review_orders(**kwargs)

    def update_pre_review_status(self, order_id, status, reviewer=None, review_remark=None):
        return self.pre_review_repo.update_pre_review_status(order_id, status, reviewer=reviewer, review_remark=review_remark)

    def update_pre_review_order(self, order_id, updates_dict):
        return self.pre_review_repo.update_pre_review_order(order_id, updates_dict)

    def create_notice_record(self, work_order_id, work_order_no, notice_type, notice_content, notice_method, notified_to, notified_phone):
        return self.pre_review_repo.create_notice_record(work_order_id, work_order_no, notice_type, notice_content, notice_method, notified_to, notified_phone)

    def list_notice_records(self, work_order_id=None, start_date=None, end_date=None, notice_method=None, limit=50, offset=0):
        return self.pre_review_repo.list_notice_records(work_order_id=work_order_id, start_date=start_date, end_date=end_date, notice_method=notice_method, limit=limit, offset=offset)

    def create_supplement_review(self, **kwargs):
        return self.pre_review_repo.create_supplement_review(**kwargs)

    def list_supplement_records(self, work_order_id: int):
        return self.pre_review_repo.list_supplement_records(work_order_id)

    def get_linked_orders(self, elder_id_card=None, contact_phone=None, item_code=None, exclude_id=None):
        return self.pre_review_repo.get_linked_orders(elder_id_card=elder_id_card, contact_phone=contact_phone, item_code=item_code, exclude_id=exclude_id)

    def find_duplicate_orders(self, item_code, elder_id_card=None, contact_phone=None, days=7):
        return self.pre_review_repo.find_duplicate_orders(item_code, elder_id_card=elder_id_card, contact_phone=contact_phone, days=days)

    def mark_expired_orders(self) -> int:
        return self.pre_review_repo.mark_expired_orders()

    def create_companion_resource(self, data):
        return self.accompany_repo.create_companion_resource(data)

    def get_companion_resource(self, resource_id: int):
        return self.accompany_repo.get_companion_resource(resource_id)

    def list_companion_resources(self, community=None, companion_type=None, is_active=None, page=1, page_size=20):
        return self.accompany_repo.list_companion_resources(community=community, companion_type=companion_type, is_active=is_active, page=page, page_size=page_size)

    def update_companion_resource(self, resource_id, data):
        return self.accompany_repo.update_companion_resource(resource_id, data)

    def delete_companion_resource(self, resource_id: int) -> bool:
        return self.accompany_repo.delete_companion_resource(resource_id)

    def get_accompany_appointment(self, appointment_id: int):
        return self.accompany_repo.get_accompany_appointment(appointment_id)

    def get_accompany_appointment_by_no(self, appointment_no: str):
        return self.accompany_repo.get_accompany_appointment_by_no(appointment_no)

    def get_match_candidates(self, appointment_id: int):
        return self.accompany_repo.get_match_candidates(appointment_id)

    def list_accompany_appointments(self, **kwargs):
        return self.accompany_repo.list_accompany_appointments(**kwargs)

    def reassign_appointment(self, appointment_id, new_companion_id, reassign_reason, operator):
        return self.accompany_repo.reassign_appointment(appointment_id, new_companion_id, reassign_reason, operator)

    def update_accompany_status(self, appointment_id, status, operator=None, remark=None):
        return self.accompany_repo.update_accompany_status(appointment_id, status, operator=operator, remark=remark)

    def cancel_appointment(self, appointment_id, cancel_reason, cancel_remark=None, operator=None):
        return self.accompany_repo.cancel_appointment(appointment_id, cancel_reason, cancel_remark=cancel_remark, operator=operator)

    def get_appointment_status_history(self, appointment_id: int):
        return self.accompany_repo.get_appointment_status_history(appointment_id)

    def create_follow_up(self, data):
        return self.accompany_repo.create_follow_up(data)

    def get_follow_ups_by_appointment(self, appointment_id: int):
        return self.accompany_repo.get_follow_ups_by_appointment(appointment_id)

    def get_exception(self, exception_id: int):
        return self.exception_repo.get_exception(exception_id)

    def get_exception_by_no(self, exception_no: str):
        return self.exception_repo.get_exception_by_no(exception_no)

    def list_exceptions(self, **kwargs):
        return self.exception_repo.list_exceptions(**kwargs)

    def update_exception_status(self, exception_id, status, operator, remark=None):
        return self.exception_repo.update_exception_status(exception_id, status, operator, remark=remark)

    def assign_exception(self, exception_id, responsible_role, responsible_person, responsible_phone, assigned_by, assign_remark=None):
        return self.exception_repo.assign_exception(exception_id, responsible_role, responsible_person, responsible_phone, assigned_by, assign_remark=assign_remark)

    def add_processing_record(self, exception_id, processor, action, result, next_step=None, duration_minutes=0):
        return self.exception_repo.add_processing_record(exception_id, processor, action, result, next_step=next_step, duration_minutes=duration_minutes)

    def close_exception(self, exception_id, closed_by, close_remark, is_resolved=True, follow_up_suggestion=None):
        return self.exception_repo.close_exception(exception_id, closed_by, close_remark, is_resolved=is_resolved, follow_up_suggestion=follow_up_suggestion)

    def get_exception_processing_records(self, exception_id: int):
        return self.exception_repo.get_exception_processing_records(exception_id)

    def get_exception_status_history(self, exception_id: int):
        return self.exception_repo.get_exception_status_history(exception_id)

    def check_source_exists(self, source_type: str, source_id: int) -> bool:
        return self.exception_repo.check_source_exists(source_type, source_id)

    def _fetch_source_info(self, source_type: str, source_id: int):
        return self.exception_repo.fetch_source_info(
            source_type, source_id,
            self.verify_repo.get_history_detail,
            self.pre_review_repo.get_pre_review_order,
            self.accompany_repo.get_accompany_appointment
        )

    def create_exception(self, data: Dict[str, Any]):
        return svc_create_exception(data, self)

    def fetch_source_info(self, source_type: str, source_id: int):
        return self.exception_repo.fetch_source_info(
            source_type, source_id,
            self.verify_repo.get_history_detail,
            self.pre_review_repo.get_pre_review_order,
            self.accompany_repo.get_accompany_appointment
        )

    def insert_exception(self, exception_no=None, exception_type=None, source_type=None, source_id=None,
                         item_code=None, item_name=None, elder_name=None, elder_type=None,
                         community=None, expected_window=None, reporter=None, reporter_role=None,
                         reporter_phone=None, description=None, location=None,
                         impact_completion=None, risk_level=None, priority=None,
                         responsible_role=None, suggested_actions=None, latest_deadline=None,
                         follow_up_required=None, follow_up_deadline=None,
                         evidence_images=None, extra_info=None, now=None):
        now_str = now.isoformat() if hasattr(now, 'isoformat') else now
        deadline_str = latest_deadline.isoformat() if hasattr(latest_deadline, 'isoformat') else latest_deadline
        fu_deadline_str = follow_up_deadline.isoformat() if follow_up_deadline and hasattr(follow_up_deadline, 'isoformat') else follow_up_deadline
        data_dict = {
            "exception_no": exception_no,
            "exception_type": exception_type,
            "source_type": source_type,
            "source_id": source_id,
            "item_code": item_code,
            "item_name": item_name,
            "elder_name": elder_name,
            "elder_type": elder_type,
            "community": community,
            "expected_window": expected_window,
            "reporter": reporter,
            "reporter_role": reporter_role,
            "reporter_phone": reporter_phone,
            "description": description,
            "location": location,
            "impact_completion": bool_to_int(impact_completion) if impact_completion is not None else 1,
            "risk_level": risk_level,
            "status": "pending",
            "priority": priority,
            "responsible_role": responsible_role,
            "suggested_actions_json": json_dumps(suggested_actions),
            "latest_deadline": deadline_str,
            "follow_up_required": bool_to_int(follow_up_required) if follow_up_required is not None else 1,
            "follow_up_deadline": fu_deadline_str,
            "evidence_images_json": json_dumps(evidence_images or []),
            "extra_info_json": json_dumps(extra_info or {}),
            "created_at": now_str,
            "updated_at": now_str
        }
        return self.exception_repo.insert_exception(data_dict)

    def insert_exception_status_history(self, exception_id=None, from_status=None, to_status=None,
                                        operator=None, remark=None, now=None, exception_no=None):
        if exception_id is None and exception_no:
            exc = self.exception_repo.get_exception_by_no(exception_no)
            if exc:
                exception_id = exc.id
        created_at = now.isoformat() if hasattr(now, 'isoformat') else now
        return self.exception_repo.insert_exception_status_history(
            exception_id, from_status, to_status, operator, remark, created_at
        )

    def create_accompany_appointment(self, data: Dict[str, Any]):
        return svc_create_accompany_appointment(data, self)

    def query_companion_candidates(self, community, item_code, expected_window=None, risk_level=None, expected_date=None):
        return self.accompany_repo.find_active_companions_for_matching(community, item_code, expected_date)

    def insert_accompany_appointment(self, appointment_no, data, item_name, expected_window_val,
                                     status, risk_level, match_priority, missing_materials,
                                     primary, expected_service_period, material_reminders,
                                     route_hints, risk_alerts, now):
        now_str = now.isoformat() if hasattr(now, 'isoformat') else now
        is_living_alone = bool_to_int(data.get("is_living_alone", False))
        primary_id = primary.companion_id if primary else None
        primary_name = primary.companion_name if primary else None
        primary_type = primary.companion_type if primary else None
        primary_phone = primary.phone if primary else None
        return self.accompany_repo.insert_appointment(
            appointment_no=appointment_no,
            elder_name=data["elder_name"],
            elder_type=data["elder_type"],
            item_code=data["item_code"],
            item_name=item_name,
            mobility_level=data["mobility_level"],
            is_living_alone=is_living_alone,
            accompany_demand_type=data["accompany_demand_type"],
            expected_date=data["expected_date"],
            community=data["community"],
            contact_phone=data["contact_phone"],
            special_notes=data.get("special_notes"),
            pre_review_order_id=data.get("pre_review_order_id"),
            verify_history_id=data.get("verify_history_id"),
            expected_window=expected_window_val,
            status=status,
            risk_level=risk_level,
            missing_materials_json=json_dumps(missing_materials),
            match_priority=match_priority,
            recommended_companion_id=primary_id,
            recommended_companion_name=primary_name,
            recommended_companion_type=primary_type,
            recommended_companion_phone=primary_phone,
            expected_service_period=expected_service_period,
            material_reminders_json=json_dumps(material_reminders),
            route_hints_json=json_dumps(route_hints),
            risk_alerts_json=json_dumps(risk_alerts),
            confirm_status="unconfirmed",
            created_at=now_str,
            updated_at=now_str
        )

    def get_appointment_id_by_no(self, appointment_no: str):
        appt = self.accompany_repo.get_accompany_appointment_by_no(appointment_no)
        return appt.id if appt else None

    def insert_match_candidate(self, appointment_id, companion, now):
        created_at = now.isoformat() if hasattr(now, 'isoformat') else now
        return self.accompany_repo.insert_match_candidates(appointment_id, [companion], created_at)

    def insert_accompany_status_history(self, appointment_id, appointment_no, from_status, to_status, operator, remark, now):
        created_at = now.isoformat() if hasattr(now, 'isoformat') else now
        return self.accompany_repo.insert_status_history(appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)

    def _match_companions(self, community, item_code, expected_window, risk_level, expected_date, limit=5):
        return svc_match_companions(self, community, item_code, expected_window, risk_level, expected_date, limit)

    def _generate_material_reminders(self, missing_materials, item_code):
        return svc_generate_material_reminders(self, missing_materials, item_code)

    def _generate_route_hints(self, community, expected_window):
        return svc_generate_route_hints(community, expected_window)

    def _generate_risk_alerts(self, risk_level, mobility_level, is_living_alone, missing_count):
        return svc_generate_risk_alerts(risk_level, mobility_level, is_living_alone, missing_count)

    def create_policy_change(self, data):
        return self.policy_repo.create_policy_change(data)

    def get_policy_change(self, policy_id: int):
        return self.policy_repo.get_policy_change(policy_id)

    def list_policy_changes(self, **kwargs):
        return self.policy_repo.list_policy_changes(**kwargs)

    def update_policy_change(self, policy_id, updates_dict):
        return self.policy_repo.update_policy_change(policy_id, updates_dict)

    def delete_policy_change(self, policy_id: int) -> bool:
        return self.policy_repo.delete_policy_change(policy_id)

    def get_policy_warning(self, warning_id: int):
        return self.policy_repo.get_policy_warning(warning_id)

    def list_policy_warnings(self, **kwargs):
        return self.policy_repo.list_policy_warnings(**kwargs)

    def confirm_policy_warning(self, warning_id, confirmed_by, confirm_remark=None):
        return self.policy_repo.confirm_policy_warning(warning_id, confirmed_by, confirm_remark=confirm_remark)

    def get_policy_warning_history(self, warning_id: int):
        return self.policy_repo.get_policy_warning_history(warning_id)

    def scan_policy_impact(self, policy_id: int):
        return svc_scan_policy_impact(policy_id, self)

    def query_policy_impact(self, elder_type=None, item_code=None, community=None, expected_window=None, appointment_date=None):
        return svc_query_policy_impact(elder_type, item_code, community, expected_window, appointment_date, self)

    def get_policy_change_detail(self, policy_id: int):
        return svc_get_policy_change_detail(policy_id, self)

    def scan_verify_records_by_items(self, applicable_items):
        with self._connect() as conn:
            c = conn.cursor()
            placeholders = ",".join("?" for _ in applicable_items)
            c.execute(f"SELECT id, item_code, item_name, elder_type FROM verification_history WHERE item_code IN ({placeholders})", list(applicable_items))
            return [dict(r) for r in c.fetchall()]

    def scan_pre_review_orders_by_items(self, applicable_items, applicable_windows, impacted_elder_types):
        with self._connect() as conn:
            c = conn.cursor()
            placeholders = ",".join("?" for _ in applicable_items)
            sql = f"SELECT id, work_order_no, item_code, item_name, elder_name, elder_type, expected_window, appointment_date FROM pre_review_orders WHERE item_code IN ({placeholders})"
            params = list(applicable_items)
            if applicable_windows:
                for w in applicable_windows:
                    sql += " AND expected_window = ?"
                    params.append(w)
            if impacted_elder_types:
                type_conditions = " OR ".join("elder_type = ?" for _ in impacted_elder_types)
                sql += f" AND ({type_conditions})"
                params.extend(impacted_elder_types)
            c.execute(sql, params)
            return [dict(r) for r in c.fetchall()]

    def scan_accompany_appointments_by_items(self, applicable_items, applicable_windows, impacted_elder_types):
        with self._connect() as conn:
            c = conn.cursor()
            placeholders = ",".join("?" for _ in applicable_items)
            sql = f"SELECT id, appointment_no, item_code, item_name, elder_name, elder_type, community, expected_window, expected_date FROM accompany_appointments WHERE item_code IN ({placeholders})"
            params = list(applicable_items)
            if applicable_windows:
                for w in applicable_windows:
                    sql += " AND expected_window = ?"
                    params.append(w)
            if impacted_elder_types:
                type_conditions = " OR ".join("elder_type = ?" for _ in impacted_elder_types)
                sql += f" AND ({type_conditions})"
                params.extend(impacted_elder_types)
            c.execute(sql, params)
            return [dict(r) for r in c.fetchall()]

    def scan_exception_orders_by_items(self, applicable_items):
        with self._connect() as conn:
            c = conn.cursor()
            placeholders = ",".join("?" for _ in applicable_items)
            c.execute(f"SELECT id, exception_no, item_code, item_name, elder_name, elder_type, community, expected_window FROM exception_disposal_orders WHERE item_code IN ({placeholders})", list(applicable_items))
            return [dict(r) for r in c.fetchall()]

    def scan_service_items_by_codes(self, applicable_items):
        with self._connect() as conn:
            c = conn.cursor()
            placeholders = ",".join("?" for _ in applicable_items)
            c.execute(f"SELECT id, item_code, item_name FROM service_items WHERE item_code IN ({placeholders})", list(applicable_items))
            return [dict(r) for r in c.fetchall()]

    def insert_policy_warning(self, policy_change_id=None, policy_title=None, source_type=None,
                              source_id=None, source_no=None, item_code=None, item_name=None,
                              elder_name=None, elder_type=None, community=None, expected_window=None,
                              appointment_date=None, risk_level=None, impact_details=None):
        return self.policy_repo.insert_policy_warning(
            policy_change_id=policy_change_id,
            policy_title=policy_title,
            source_type=source_type,
            source_id=source_id,
            source_no=source_no,
            item_code=item_code,
            item_name=item_name,
            elder_name=elder_name,
            elder_type=elder_type,
            community=community,
            expected_window=expected_window,
            appointment_date=appointment_date,
            risk_level=risk_level,
            status="unconfirmed",
            impact_details=impact_details or [],
            created_at=now_iso()
        )

    def query_active_policies(self, elder_type=None, item_code=None, expected_window=None):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.policy_repo.get_active_policies(
            today=today,
            item_code=item_code,
            expected_window=expected_window,
            elder_type=elder_type
        )

    def list_warnings_by_policy_id(self, policy_change_id: int):
        result = self.policy_repo.list_policy_warnings(policy_change_id=policy_change_id, page=1, page_size=10000)
        return result.get("items", [])

    def get_overall_stats(self, item_code=None, limit_items=10, limit_materials=10):
        return self.stats_repo.get_overall_stats(item_code=item_code, limit_items=limit_items, limit_materials=limit_materials)

    def get_pre_review_stats(self, item_code=None, expected_window=None, start_date=None, end_date=None):
        return self.stats_repo.get_pre_review_stats(item_code=item_code, expected_window=expected_window, start_date=start_date, end_date=end_date)

    def get_accompany_stats(self, community=None, start_date=None, end_date=None):
        return self.stats_repo.get_accompany_stats(community=community, start_date=start_date, end_date=end_date)

    def get_exception_stats(self, item_code=None, community=None, expected_window=None, start_date=None, end_date=None):
        return self.stats_repo.get_exception_stats(item_code=item_code, community=community, expected_window=expected_window, start_date=start_date, end_date=end_date)

    def get_policy_stats(self, item_code=None, community=None, expected_window=None, start_date=None, end_date=None):
        return self.stats_repo.get_policy_stats(item_code=item_code, community=community, expected_window=expected_window, start_date=start_date, end_date=end_date)
