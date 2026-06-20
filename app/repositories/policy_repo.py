from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import BaseRepository
from ..db_utils import json_dumps, json_loads, bool_to_int, int_to_bool, now_iso, enum_value, QueryBuilder, paginate_result
from ..schemas import PolicyChange, PolicyWarning


_POLICY_CHANGE_JSON_FIELDS = {
    "applicable_items": "applicable_items_json",
    "applicable_windows": "applicable_windows_json",
    "impacted_materials": "impacted_materials_json",
    "impacted_elder_types": "impacted_elder_types_json",
    "impact_types": "impact_types_json",
    "added_materials": "added_materials_json",
    "removed_materials": "removed_materials_json",
    "rejection_reasons": "rejection_reasons_json",
}


def _row_to_policy_change(row) -> PolicyChange:
    return PolicyChange(
        id=row["id"],
        title=row["title"],
        applicable_items=json_loads(row["applicable_items_json"]),
        applicable_windows=json_loads(row["applicable_windows_json"]),
        impacted_materials=json_loads(row["impacted_materials_json"]),
        impacted_elder_types=json_loads(row["impacted_elder_types_json"]),
        effective_date=row["effective_date"],
        expiry_date=row["expiry_date"],
        policy_source=row["policy_source"],
        risk_level=row["risk_level"],
        handling_suggestion=row["handling_suggestion"],
        impact_types=json_loads(row["impact_types_json"]),
        description=row["description"],
        added_materials=json_loads(row["added_materials_json"]),
        removed_materials=json_loads(row["removed_materials_json"]),
        rejection_reasons=json_loads(row["rejection_reasons_json"]),
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"])
    )


def _row_to_policy_warning(row) -> PolicyWarning:
    return PolicyWarning(
        id=row["id"],
        policy_change_id=row["policy_change_id"],
        policy_title=row["policy_title"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        source_no=row["source_no"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        elder_name=row["elder_name"],
        elder_type=row["elder_type"],
        community=row["community"],
        expected_window=row["expected_window"],
        appointment_date=row["appointment_date"],
        risk_level=row["risk_level"],
        status=row["status"],
        impact_details=json_loads(row["impact_details_json"]),
        confirmed_at=row["confirmed_at"],
        confirmed_by=row["confirmed_by"],
        confirm_remark=row["confirm_remark"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


class PolicyRepository(BaseRepository):

    def create_policy_change(self, data: Dict[str, Any]) -> PolicyChange:
        now = now_iso()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO policy_changes
                (title, applicable_items_json, applicable_windows_json, impacted_materials_json,
                 impacted_elder_types_json, effective_date, expiry_date, policy_source,
                 risk_level, handling_suggestion, impact_types_json, description,
                 added_materials_json, removed_materials_json, rejection_reasons_json,
                 status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("title", ""),
                json_dumps(data.get("applicable_items", [])),
                json_dumps(data.get("applicable_windows", [])),
                json_dumps(data.get("impacted_materials", [])),
                json_dumps(data.get("impacted_elder_types", [])),
                data.get("effective_date", ""),
                data.get("expiry_date"),
                data.get("policy_source", ""),
                enum_value(data.get("risk_level", "medium")),
                data.get("handling_suggestion", ""),
                json_dumps(data.get("impact_types", [])),
                data.get("description", ""),
                json_dumps(data.get("added_materials", [])),
                json_dumps(data.get("removed_materials", [])),
                json_dumps(data.get("rejection_reasons", [])),
                enum_value(data.get("status", "draft")),
                now, now
            ))
            new_id = c.lastrowid
            c.execute("SELECT * FROM policy_changes WHERE id = ?", (new_id,))
            return _row_to_policy_change(c.fetchone())

    def get_policy_change(self, policy_id: int) -> Optional[PolicyChange]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM policy_changes WHERE id = ?", (policy_id,))
            row = c.fetchone()
            return _row_to_policy_change(row) if row else None

    def list_policy_changes(
        self,
        item_code: Optional[str] = None,
        expected_window: Optional[str] = None,
        risk_level: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        qb = QueryBuilder("policy_changes")
        if item_code:
            qb.json_like("applicable_items_json", item_code)
        if expected_window:
            qb.json_like("applicable_windows_json", expected_window)
        if risk_level:
            qb.eq("risk_level", risk_level)
        if status:
            qb.eq("status", status)
        if start_date:
            qb.date_gte("effective_date", start_date)
        if end_date:
            qb.date_lte("effective_date", end_date)
        extra_where = ""
        extra_params = []
        if keyword:
            extra_where = "(title LIKE ? OR description LIKE ? OR policy_source LIKE ?)"
            extra_params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]
        data_sql, data_params, count_sql, count_params = qb.build_paginated(
            page=page, page_size=page_size,
            extra_where=extra_where, extra_params=extra_params
        )
        with self._connect() as conn:
            return paginate_result(
                conn, _row_to_policy_change,
                data_sql, data_params, count_sql, count_params,
                page, page_size
            )

    def update_policy_change(self, policy_id: int, updates_dict: Dict[str, Any]) -> Optional[PolicyChange]:
        existing = self.get_policy_change(policy_id)
        if not existing:
            return None
        now = now_iso()
        updates = ["updated_at = ?"]
        params = [now]
        for key, value in updates_dict.items():
            if key in _POLICY_CHANGE_JSON_FIELDS:
                col = _POLICY_CHANGE_JSON_FIELDS[key]
                updates.append(f"{col} = ?")
                params.append(json_dumps(value))
            elif key in ("status", "risk_level"):
                updates.append(f"{key} = ?")
                params.append(enum_value(value))
            elif key not in ("id", "created_at", "updated_at"):
                updates.append(f"{key} = ?")
                params.append(value)
        params.append(policy_id)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(f"UPDATE policy_changes SET {', '.join(updates)} WHERE id = ?", params)
        return self.get_policy_change(policy_id)

    def delete_policy_change(self, policy_id: int) -> bool:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM policy_changes WHERE id = ?", (policy_id,))
            return c.rowcount > 0

    def get_policy_warning(self, warning_id: int) -> Optional[PolicyWarning]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM policy_warnings WHERE id = ?", (warning_id,))
            row = c.fetchone()
            return _row_to_policy_warning(row) if row else None

    def list_policy_warnings(
        self,
        policy_change_id: Optional[int] = None,
        source_type: Optional[str] = None,
        item_code: Optional[str] = None,
        community: Optional[str] = None,
        expected_window: Optional[str] = None,
        risk_level: Optional[str] = None,
        status: Optional[str] = None,
        elder_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        qb = QueryBuilder("policy_warnings")
        if policy_change_id:
            qb.eq("policy_change_id", policy_change_id)
        if source_type:
            qb.eq("source_type", source_type)
        if item_code:
            qb.eq("item_code", item_code)
        if community:
            qb.eq("community", community)
        if expected_window:
            qb.eq("expected_window", expected_window)
        if risk_level:
            qb.eq("risk_level", risk_level)
        if status:
            qb.eq("status", status)
        if elder_name:
            qb.like("elder_name", elder_name)
        if start_date:
            qb.date_gte("created_at", start_date)
        if end_date:
            qb.date_lte("created_at", end_date)
        data_sql, data_params, count_sql, count_params = qb.build_paginated(
            page=page, page_size=page_size
        )
        with self._connect() as conn:
            return paginate_result(
                conn, _row_to_policy_warning,
                data_sql, data_params, count_sql, count_params,
                page, page_size
            )

    def confirm_policy_warning(self, warning_id: int, confirmed_by: str, confirm_remark: Optional[str] = None) -> Optional[PolicyWarning]:
        existing = self.get_policy_warning(warning_id)
        if not existing:
            return None
        now = now_iso()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE policy_warnings
                SET status = 'confirmed', confirmed_at = ?, confirmed_by = ?, confirm_remark = ?
                WHERE id = ?
            """, (now, confirmed_by, confirm_remark, warning_id))
            c.execute("""
                INSERT INTO policy_warning_history
                (warning_id, from_status, to_status, operator, remark, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (warning_id, existing.status, "confirmed", confirmed_by, confirm_remark, now))
        return self.get_policy_warning(warning_id)

    def get_policy_warning_history(self, warning_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM policy_warning_history
                WHERE warning_id = ?
                ORDER BY created_at ASC
            """, (warning_id,))
            records = []
            for r in c.fetchall():
                records.append({
                    "id": r["id"],
                    "warning_id": r["warning_id"],
                    "from_status": r["from_status"],
                    "to_status": r["to_status"],
                    "operator": r["operator"],
                    "remark": r["remark"],
                    "created_at": r["created_at"]
                })
            return records

    def insert_policy_warning(
        self,
        policy_change_id: int,
        policy_title: str,
        source_type: str,
        source_id: int,
        source_no: Optional[str],
        item_code: Optional[str],
        item_name: Optional[str],
        elder_name: Optional[str],
        elder_type: Optional[str],
        community: Optional[str],
        expected_window: Optional[str],
        appointment_date: Optional[str],
        risk_level: str,
        status: str,
        impact_details: List[Dict],
        created_at: str
    ) -> int:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO policy_warnings
                (policy_change_id, policy_title, source_type, source_id, source_no,
                 item_code, item_name, elder_name, elder_type, community,
                 expected_window, appointment_date, risk_level, status,
                 impact_details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                policy_change_id, policy_title, source_type, source_id, source_no,
                item_code, item_name, elder_name, elder_type, community,
                expected_window, appointment_date, risk_level, status,
                json_dumps(impact_details), created_at
            ))
            return c.lastrowid

    def check_warning_exists(self, policy_change_id: int, source_type: str, source_id: int) -> bool:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) as cnt FROM policy_warnings
                WHERE policy_change_id = ? AND source_type = ? AND source_id = ?
            """, (policy_change_id, source_type, source_id))
            return c.fetchone()["cnt"] > 0

    def get_active_policies(
        self,
        today: str,
        item_code: Optional[str] = None,
        expected_window: Optional[str] = None,
        elder_type: Optional[str] = None
    ) -> List[PolicyChange]:
        sql = "SELECT * FROM policy_changes WHERE status = 'active' AND effective_date <= ?"
        params: list = [today]
        if item_code:
            sql += " AND applicable_items_json LIKE ?"
            params.append(f'%"{item_code}"%')
        if expected_window:
            sql += " AND applicable_windows_json LIKE ?"
            params.append(f'%"{expected_window}"%')
        if elder_type:
            sql += " AND impacted_elder_types_json LIKE ?"
            params.append(f'%"{elder_type}"%')
        sql += " ORDER BY effective_date DESC"
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(sql, params)
            return [_row_to_policy_change(r) for r in c.fetchall()]
