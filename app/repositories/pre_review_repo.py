from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from .base import BaseRepository
from ..db_utils import json_dumps, json_loads, bool_to_int, int_to_bool, now_iso, enum_value, generate_no
from ..schemas import PreReviewWorkOrder, OneTimeNoticeRecord


def _row_to_pre_review_order(row) -> PreReviewWorkOrder:
    return PreReviewWorkOrder(
        id=row["id"],
        work_order_no=row["work_order_no"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        elder_type=row["elder_type"],
        elder_id_card=row["elder_id_card"],
        elder_name=row["elder_name"],
        is_agent=int_to_bool(row["is_agent"]),
        agent_relation=row["agent_relation"],
        agent_name=row["agent_name"],
        contact_phone=row["contact_phone"],
        expected_window=row["expected_window"],
        appointment_date=row["appointment_date"],
        remarks=row["remarks"],
        status=row["status"],
        risk_level=row["risk_level"],
        is_pass=int_to_bool(row["is_pass"]),
        total_required=row["total_required"],
        total_missing=row["total_missing"],
        total_ready=row["total_ready"],
        one_time_notice=row["one_time_notice"],
        suggestion_deadline=datetime.fromisoformat(row["suggestion_deadline"]),
        window_notes=json_loads(row["window_notes_json"]),
        missing_list_json=row["missing_list_json"],
        ready_materials_json=row["ready_materials_json"],
        check_summary_json=row["check_summary_json"],
        is_duplicate=int_to_bool(row["is_duplicate"]),
        linked_original_id=row["linked_original_id"],
        review_count=row["review_count"],
        supplement_count=row["supplement_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        reviewer=row["reviewer"],
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None
    )


def _row_to_notice_record(row) -> OneTimeNoticeRecord:
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


class PreReviewRepository(BaseRepository):

    def create_pre_review_order(
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
        work_order_no = generate_no("PR", now)
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
                bool_to_int(is_agent), agent_relation, agent_name, contact_phone, expected_window,
                appointment_date, remarks, status, risk_level, bool_to_int(is_pass), total_required,
                total_missing, total_ready, one_time_notice, suggestion_deadline.isoformat(),
                json_dumps(window_notes),
                json_dumps(missing_list),
                json_dumps(ready_materials),
                json_dumps(check_summary),
                bool_to_int(is_duplicate), linked_original_id, bool_to_int(is_pass), 0,
                now.isoformat(), now.isoformat()
            ))
            new_id = c.lastrowid
            c.execute("SELECT * FROM pre_review_orders WHERE id = ?", (new_id,))
            return _row_to_pre_review_order(c.fetchone())

    def find_duplicate_orders(
        self,
        item_code: str,
        elder_id_card: Optional[str] = None,
        contact_phone: Optional[str] = None,
        days: int = 7
    ) -> List[PreReviewWorkOrder]:
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

    def get_pre_review_order(self, order_id: int) -> Optional[PreReviewWorkOrder]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM pre_review_orders WHERE id = ?", (order_id,))
            row = c.fetchone()
            return _row_to_pre_review_order(row) if row else None

    def get_pre_review_by_no(self, work_order_no: str) -> Optional[PreReviewWorkOrder]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM pre_review_orders WHERE work_order_no = ?", (work_order_no,))
            row = c.fetchone()
            return _row_to_pre_review_order(row) if row else None

    def list_pre_review_orders(
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
            params.append(bool_to_int(is_duplicate))
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

    def update_pre_review_status(
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

    def update_pre_review_order(
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
                params.append(json_dumps(value))
            elif key == "suggestion_deadline":
                updates.append("suggestion_deadline = ?")
                params.append(value.isoformat() if isinstance(value, datetime) else value)
            elif key == "is_pass":
                updates.append("is_pass = ?")
                params.append(bool_to_int(value))
            elif key == "is_agent":
                updates.append("is_agent = ?")
                params.append(bool_to_int(value))
            elif key == "is_duplicate":
                updates.append("is_duplicate = ?")
                params.append(bool_to_int(value))
            elif key not in ("id", "work_order_no", "created_at"):
                updates.append(f"{key} = ?")
                params.append(value)
        params.append(order_id)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(f"UPDATE pre_review_orders SET {', '.join(updates)} WHERE id = ?", params)
        return self.get_pre_review_order(order_id)

    def create_notice_record(
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

    def list_notice_records(
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

    def create_supplement_review(
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
                work_order_id, work_order_no, reviewer, bool_to_int(review_result),
                missing_before, missing_after, review_remark or "",
                json_dumps(supplemented_materials or []),
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

    def list_supplement_records(self, work_order_id: int) -> List[Dict[str, Any]]:
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
                    "review_result": int_to_bool(r["review_result"]),
                    "missing_before": r["missing_before"],
                    "missing_after": r["missing_after"],
                    "review_remark": r["review_remark"],
                    "supplemented_materials": json_loads(r["supplemented_materials_json"]),
                    "created_at": r["created_at"]
                })
            return records

    def get_linked_orders(self, elder_id_card: Optional[str] = None, contact_phone: Optional[str] = None, item_code: Optional[str] = None, exclude_id: Optional[int] = None) -> List[Dict[str, Any]]:
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

    def mark_expired_orders(self) -> int:
        now_str = now_iso()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE pre_review_orders
                SET status = 'expired', updated_at = ?
                WHERE status NOT IN ('passed', 'completed', 'expired', 'rejected')
                  AND is_pass = 0
                  AND suggestion_deadline < ?
            """, (now_str, now_str))
            return c.rowcount
