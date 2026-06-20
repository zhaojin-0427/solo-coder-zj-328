from typing import List, Optional, Dict
from datetime import datetime

from .base import BaseRepository
from ..db_utils import json_dumps, json_loads, bool_to_int, int_to_bool, now_iso, enum_value
from ..schemas import (
    ServiceItemCreate, ServiceItemUpdate, ServiceItem,
    MaterialSpec, SpecialNote, HistoryRecord,
    ElderType, MaterialCategory, PhotoSpec
)


class VerifyRepository(BaseRepository):

    def _parse_material_spec(self, data: dict) -> MaterialSpec:
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

    def _parse_special_note(self, data: dict) -> SpecialNote:
        extra = [self._parse_material_spec(m) for m in data.get("extra_materials", [])]
        return SpecialNote(
            elder_type=ElderType(data["elder_type"]),
            note=data.get("note", ""),
            extra_materials=extra
        )

    def _row_to_service_item(self, row) -> ServiceItem:
        base = json_loads(row["base_materials"])
        agent = json_loads(row["agent_required_materials"])
        special = json_loads(row["special_notes"])
        return ServiceItem(
            id=row["id"],
            item_code=row["item_code"],
            item_name=row["item_name"],
            description=row["description"],
            base_materials=[self._parse_material_spec(m) for m in base],
            agent_required_materials=[self._parse_material_spec(m) for m in agent],
            special_notes=[self._parse_special_note(n) for n in special],
            enabled=int_to_bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    def _row_to_history(self, row) -> HistoryRecord:
        return HistoryRecord(
            id=row["id"],
            item_code=row["item_code"],
            item_name=row["item_name"],
            elder_type=row["elder_type"],
            is_agent=int_to_bool(row["is_agent"]),
            agent_relation=row["agent_relation"],
            is_pass=int_to_bool(row["is_pass"]),
            missing_count=row["missing_count"],
            missing_categories=row["missing_categories"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
            make_up_count=row["make_up_count"] or 0
        )

    def has_items(self) -> bool:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM service_items")
            return c.fetchone()["cnt"] > 0

    def seed_default_items(self, default_items: List[ServiceItemCreate]):
        if self.has_items():
            return
        now = now_iso()
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
                    json_dumps([m.model_dump() for m in item.base_materials]),
                    json_dumps([m.model_dump() for m in item.agent_required_materials]),
                    json_dumps([n.model_dump() for n in item.special_notes]),
                    bool_to_int(item.enabled),
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
            return [self._row_to_service_item(r) for r in c.fetchall()]

    def get_item(self, item_code: str) -> Optional[ServiceItem]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM service_items WHERE item_code = ?", (item_code,))
            row = c.fetchone()
            return self._row_to_service_item(row) if row else None

    def create_item(self, data: ServiceItemCreate) -> ServiceItem:
        now = now_iso()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO service_items
                (item_code, item_name, description, base_materials, agent_required_materials,
                 special_notes, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.item_code, data.item_name, data.description,
                json_dumps([m.model_dump() for m in data.base_materials]),
                json_dumps([m.model_dump() for m in data.agent_required_materials]),
                json_dumps([n.model_dump() for n in data.special_notes]),
                bool_to_int(data.enabled),
                now, now
            ))
            new_id = c.lastrowid
            c.execute("SELECT * FROM service_items WHERE id = ?", (new_id,))
            return self._row_to_service_item(c.fetchone())

    def update_item(self, item_code: str, data: ServiceItemUpdate) -> Optional[ServiceItem]:
        existing = self.get_item(item_code)
        if not existing:
            return None
        now = now_iso()
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
            params.append(json_dumps([m.model_dump() for m in data.base_materials]))
        if data.agent_required_materials is not None:
            updates.append("agent_required_materials = ?")
            params.append(json_dumps([m.model_dump() for m in data.agent_required_materials]))
        if data.special_notes is not None:
            updates.append("special_notes = ?")
            params.append(json_dumps([n.model_dump() for n in data.special_notes]))
        if data.enabled is not None:
            updates.append("enabled = ?")
            params.append(bool_to_int(data.enabled))
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
        now = now_iso()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO verification_history
                (item_code, item_name, elder_type, is_agent, agent_relation,
                 is_pass, missing_count, missing_categories, missing_details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_code, item_name, elder_type,
                bool_to_int(is_agent),
                agent_relation,
                bool_to_int(is_pass),
                missing_count,
                json_dumps(missing_categories, ensure_ascii=False),
                json_dumps(missing_details, ensure_ascii=False),
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
        now = now_iso()
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
            params.append(bool_to_int(is_pass))
        if is_agent is not None:
            sql += " AND is_agent = ?"
            params.append(bool_to_int(is_agent))
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
            return [self._row_to_history(r) for r in c.fetchall()]

    def get_history_detail(self, history_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM verification_history WHERE id = ?", (history_id,))
            row = c.fetchone()
            if not row:
                return None
            record = self._row_to_history(row)
            details_json = json_loads(row["missing_details_json"])
            return {
                "record": record,
                "missing_details": details_json
            }
