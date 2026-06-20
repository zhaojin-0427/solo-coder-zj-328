import sqlite3
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import BaseRepository
from ..db_utils import json_dumps, json_loads, bool_to_int, int_to_bool, now_iso, enum_value
from ..schemas import (
    ExceptionDisposalOrder, ExceptionProcessingRecord, ExceptionStatusHistory
)


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
        impact_completion=int_to_bool(row["impact_completion"]),
        risk_level=row["risk_level"],
        status=row["status"],
        priority=row["priority"],
        responsible_role=row["responsible_role"],
        responsible_person=row["responsible_person"],
        responsible_phone=row["responsible_phone"],
        suggested_actions=json_loads(row["suggested_actions_json"], []),
        latest_deadline=datetime.fromisoformat(row["latest_deadline"]),
        follow_up_required=int_to_bool(row["follow_up_required"]),
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


class ExceptionRepository(BaseRepository):

    def get_exception(self, exception_id: int) -> Optional[ExceptionDisposalOrder]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM exception_disposal_orders WHERE id = ?", (exception_id,))
            row = c.fetchone()
            return _row_to_exception_order(row) if row else None

    def get_exception_by_no(self, exception_no: str) -> Optional[ExceptionDisposalOrder]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM exception_disposal_orders WHERE exception_no = ?", (exception_no,))
            row = c.fetchone()
            return _row_to_exception_order(row) if row else None

    def list_exceptions(
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

    def insert_exception(self, data_dict: Dict[str, Any]) -> int:
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
                data_dict["exception_no"],
                data_dict["exception_type"],
                data_dict["source_type"],
                data_dict["source_id"],
                data_dict.get("item_code"),
                data_dict.get("item_name"),
                data_dict.get("elder_name"),
                data_dict.get("elder_type"),
                data_dict.get("community"),
                data_dict.get("expected_window"),
                data_dict["reporter"],
                data_dict["reporter_role"],
                data_dict.get("reporter_phone"),
                data_dict["description"],
                data_dict.get("location"),
                data_dict["impact_completion"],
                data_dict["risk_level"],
                data_dict["status"],
                data_dict["priority"],
                data_dict["responsible_role"],
                data_dict["suggested_actions_json"],
                data_dict["latest_deadline"],
                data_dict["follow_up_required"],
                data_dict.get("follow_up_deadline"),
                data_dict.get("evidence_images_json"),
                data_dict.get("extra_info_json"),
                data_dict["created_at"],
                data_dict["updated_at"]
            ))
            return c.lastrowid

    def insert_exception_status_history(
        self,
        exception_id: int,
        from_status: Optional[str],
        to_status: str,
        operator: str,
        remark: Optional[str],
        created_at: str
    ):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO exception_status_history
                (exception_id, from_status, to_status, operator, remark, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (exception_id, from_status, to_status, operator, remark, created_at))

    def update_exception_status(
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

    def assign_exception(
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

    def add_processing_record(
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

    def close_exception(
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

    def get_exception_processing_records(self, exception_id: int) -> List[ExceptionProcessingRecord]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM exception_processing_records
                WHERE exception_id = ? ORDER BY created_at DESC
            """, (exception_id,))
            return [_row_to_processing_record(r) for r in c.fetchall()]

    def get_exception_status_history(self, exception_id: int) -> List[ExceptionStatusHistory]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM exception_status_history
                WHERE exception_id = ? ORDER BY created_at ASC
            """, (exception_id,))
            return [_row_to_status_history(r) for r in c.fetchall()]

    def check_source_exists(self, source_type: str, source_id: int) -> bool:
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

    def fetch_source_info(
        self,
        source_type: str,
        source_id: int,
        get_history_detail_func,
        get_pre_review_order_func,
        get_accompany_appointment_func
    ) -> Optional[Dict[str, Any]]:
        if source_type == "verify_record":
            return get_history_detail_func(source_id)
        elif source_type == "pre_review_order":
            order = get_pre_review_order_func(source_id)
            return order.model_dump(mode="json") if order else None
        elif source_type == "accompany_appointment":
            appt = get_accompany_appointment_func(source_id)
            return appt.model_dump(mode="json") if appt else None
        return None
