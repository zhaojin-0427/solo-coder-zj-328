import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import BaseRepository
from ..db_utils import json_dumps, json_loads, bool_to_int, int_to_bool, now_iso, enum_value, generate_no
from ..schemas import (
    CompanionResource, CompanionResourceCreate, CompanionResourceUpdate,
    AccompanyAppointment, MatchedCompanion, AccompanyFollowUpRecord
)


def _row_to_companion_resource(row: sqlite3.Row) -> CompanionResource:
    return CompanionResource(
        id=row["id"],
        name=row["name"],
        companion_type=row["companion_type"],
        community=row["community"],
        phone=row["phone"],
        id_card=row["id_card"],
        available_windows=json_loads(row["available_windows_json"], []),
        eligible_items=json_loads(row["eligible_items_json"], []),
        max_daily_count=row["max_daily_count"],
        skills=json_loads(row["skills_json"], []),
        is_active=int_to_bool(row["is_active"]),
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
        is_living_alone=int_to_bool(row["is_living_alone"]),
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
        missing_materials=json_loads(row["missing_materials_json"], []),
        match_priority=row["match_priority"],
        recommended_companion_id=row["recommended_companion_id"],
        recommended_companion_name=row["recommended_companion_name"],
        recommended_companion_type=row["recommended_companion_type"],
        recommended_companion_phone=row["recommended_companion_phone"],
        expected_service_period=row["expected_service_period"],
        material_reminders=json_loads(row["material_reminders_json"], []),
        route_hints=json_loads(row["route_hints_json"], []),
        risk_alerts=json_loads(row["risk_alerts_json"], []),
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
        is_companion_arrived=int_to_bool(row["is_companion_arrived"]),
        is_elder_satisfied=int_to_bool(row["is_elder_satisfied"]),
        materials_completed=int_to_bool(row["materials_completed"]),
        failed_materials=json_loads(row["failed_materials_json"], []),
        service_duration_minutes=row["service_duration_minutes"],
        issues=json_loads(row["issues_json"], []),
        suggestions=row["suggestions"],
        follower=row["follower"],
        created_at=datetime.fromisoformat(row["created_at"])
    )


class AccompanyRepository(BaseRepository):

    def create_companion_resource(self, data: CompanionResourceCreate) -> CompanionResource:
        now = now_iso()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO companion_resources
                (name, companion_type, community, phone, id_card, available_windows_json,
                 eligible_items_json, max_daily_count, skills_json, is_active, remarks,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.name, enum_value(data.companion_type), data.community, data.phone, data.id_card,
                json_dumps([enum_value(w) for w in data.available_windows]),
                json_dumps(data.eligible_items),
                data.max_daily_count,
                json_dumps(data.skills),
                bool_to_int(data.is_active),
                data.remarks,
                now, now
            ))
            new_id = c.lastrowid
            c.execute("SELECT * FROM companion_resources WHERE id = ?", (new_id,))
            return _row_to_companion_resource(c.fetchone())

    def get_companion_resource(self, resource_id: int) -> Optional[CompanionResource]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM companion_resources WHERE id = ?", (resource_id,))
            row = c.fetchone()
            return _row_to_companion_resource(row) if row else None

    def list_companion_resources(
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
            params.append(bool_to_int(is_active))
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

    def update_companion_resource(
        self,
        resource_id: int,
        data: CompanionResourceUpdate
    ) -> Optional[CompanionResource]:
        existing = self.get_companion_resource(resource_id)
        if not existing:
            return None
        now = now_iso()
        updates = ["updated_at = ?"]
        params = [now]
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name)
        if data.companion_type is not None:
            updates.append("companion_type = ?")
            params.append(enum_value(data.companion_type))
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
            params.append(json_dumps([enum_value(w) for w in data.available_windows]))
        if data.eligible_items is not None:
            updates.append("eligible_items_json = ?")
            params.append(json_dumps(data.eligible_items))
        if data.max_daily_count is not None:
            updates.append("max_daily_count = ?")
            params.append(data.max_daily_count)
        if data.skills is not None:
            updates.append("skills_json = ?")
            params.append(json_dumps(data.skills))
        if data.is_active is not None:
            updates.append("is_active = ?")
            params.append(bool_to_int(data.is_active))
        if data.remarks is not None:
            updates.append("remarks = ?")
            params.append(data.remarks)
        params.append(resource_id)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(f"UPDATE companion_resources SET {', '.join(updates)} WHERE id = ?", params)
        return self.get_companion_resource(resource_id)

    def delete_companion_resource(self, resource_id: int) -> bool:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM companion_resources WHERE id = ?", (resource_id,))
            return c.rowcount > 0

    def get_accompany_appointment(self, appointment_id: int) -> Optional[AccompanyAppointment]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM accompany_appointments WHERE id = ?", (appointment_id,))
            row = c.fetchone()
            return _row_to_accompany_appointment(row) if row else None

    def get_accompany_appointment_by_no(self, appointment_no: str) -> Optional[AccompanyAppointment]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM accompany_appointments WHERE appointment_no = ?", (appointment_no,))
            row = c.fetchone()
            return _row_to_accompany_appointment(row) if row else None

    def get_match_candidates(self, appointment_id: int) -> List[MatchedCompanion]:
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
                    match_reasons=json_loads(r["match_reasons_json"], [])
                ))
            return results

    def list_accompany_appointments(
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

    def reassign_appointment(
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

    def update_accompany_status(
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

    def cancel_appointment(
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

    def get_appointment_status_history(self, appointment_id: int) -> List[Dict[str, Any]]:
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

    def create_follow_up(self, data: Dict[str, Any]) -> AccompanyFollowUpRecord:
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
                bool_to_int(data.get("is_companion_arrived")),
                bool_to_int(data.get("is_elder_satisfied")),
                bool_to_int(data.get("materials_completed")),
                json_dumps(data.get("failed_materials", [])),
                data.get("service_duration_minutes", 0),
                json_dumps(data.get("issues", [])),
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

    def get_follow_ups_by_appointment(self, appointment_id: int) -> List[AccompanyFollowUpRecord]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM accompany_follow_ups
                WHERE appointment_id = ?
                ORDER BY created_at DESC
            """, (appointment_id,))
            return [_row_to_follow_up(r) for r in c.fetchall()]

    def insert_appointment(
        self,
        appointment_no: str,
        elder_name: str,
        elder_type: str,
        item_code: str,
        item_name: str,
        mobility_level: str,
        is_living_alone: int,
        accompany_demand_type: str,
        expected_date: str,
        community: str,
        contact_phone: str,
        special_notes: Optional[str],
        pre_review_order_id: Optional[int],
        verify_history_id: Optional[int],
        expected_window: Optional[str],
        status: str,
        risk_level: str,
        missing_materials_json: str,
        match_priority: int,
        recommended_companion_id: Optional[int],
        recommended_companion_name: Optional[str],
        recommended_companion_type: Optional[str],
        recommended_companion_phone: Optional[str],
        expected_service_period: str,
        material_reminders_json: str,
        route_hints_json: str,
        risk_alerts_json: str,
        confirm_status: str,
        created_at: str,
        updated_at: str
    ) -> int:
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
                appointment_no, elder_name, elder_type, item_code, item_name, mobility_level,
                is_living_alone, accompany_demand_type, expected_date, community, contact_phone,
                special_notes, pre_review_order_id, verify_history_id, expected_window,
                status, risk_level, missing_materials_json, match_priority,
                recommended_companion_id, recommended_companion_name, recommended_companion_type,
                recommended_companion_phone, expected_service_period,
                material_reminders_json, route_hints_json, risk_alerts_json,
                confirm_status, created_at, updated_at
            ))
            return c.lastrowid

    def insert_match_candidates(
        self,
        appointment_id: int,
        candidates: List[MatchedCompanion],
        created_at: str
    ) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            for m in candidates:
                c.execute("""
                    INSERT INTO accompany_match_candidates
                    (appointment_id, companion_id, match_priority, match_score, match_reasons_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    appointment_id, m.companion_id, m.match_priority, m.match_score,
                    json_dumps(m.match_reasons),
                    created_at
                ))

    def insert_status_history(
        self,
        appointment_id: int,
        appointment_no: str,
        from_status: Optional[str],
        to_status: str,
        operator: str,
        remark: str,
        created_at: str
    ) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO accompany_status_history
                (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (appointment_id, appointment_no, from_status, to_status, operator, remark, created_at))

    def find_active_companions_for_matching(
        self,
        community: str,
        item_code: str,
        expected_date: str
    ) -> List[Dict[str, Any]]:
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
            return [dict(r) for r in c.fetchall()]
