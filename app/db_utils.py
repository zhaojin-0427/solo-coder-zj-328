import json
import sqlite3
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from contextlib import contextmanager

from .schemas import UniformResponse, CodeEnum


class DictEncoder(json.JSONEncoder):
    def default(self, obj):
        from .schemas import (
            ElderType, AgentRelation, MaterialCategory, PhotoSpec,
            MobilityLevel, AccompanyDemandType, CompanionType,
            AppointmentStatus, ConfirmStatus,
            ExceptionType, ExceptionStatus, DisposalPriority,
            ResponsibleRole, ExceptionSourceType,
            PolicyChangeStatus, PolicyRiskLevel, PolicyImpactType,
            WarningStatus, WarningSourceType, RiskLevel, ServiceWindow
        )
        if isinstance(obj, (
            ElderType, AgentRelation, MaterialCategory, PhotoSpec,
            MobilityLevel, AccompanyDemandType, CompanionType,
            AppointmentStatus, ConfirmStatus, RiskLevel, ServiceWindow,
            ExceptionType, ExceptionStatus, DisposalPriority,
            ResponsibleRole, ExceptionSourceType,
            PolicyChangeStatus, PolicyRiskLevel, PolicyImpactType,
            WarningStatus, WarningSourceType
        )):
            return obj.value
        return super().default(obj)


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


def enum_value(val):
    if val is None:
        return None
    return val.value if hasattr(val, "value") else val


def json_dumps(obj, ensure_ascii=False, cls=None):
    if cls is None:
        cls = DictEncoder
    return json.dumps(obj, cls=cls, ensure_ascii=ensure_ascii)


def json_loads(s, default=None):
    if not s:
        return default if default is not None else []
    if isinstance(s, str):
        return json.loads(s)
    return s


def bool_to_int(val):
    return 1 if val else 0


def int_to_bool(val):
    return bool(val)


def now_iso():
    return datetime.now().isoformat()


def generate_no(prefix: str, dt: datetime) -> str:
    return f"{prefix}{dt.strftime('%Y%m%d%H%M%S')}{dt.microsecond // 1000:03d}"


class QueryBuilder:
    def __init__(self, table: str):
        self._table = table
        self._conditions = []
        self._params = []
        self._count_params = None

    def eq(self, column: str, value, count_column: str = None):
        if value is None:
            return self
        self._conditions.append((column, "=", value))
        return self

    def like(self, column: str, value, count_column: str = None):
        if not value:
            return self
        self._conditions.append((column, "LIKE", f"%{value}%"))
        return self

    def date_gte(self, column: str, value):
        if not value:
            return self
        self._conditions.append((f"date({column})", ">=", value, "date(?)"))
        return self

    def date_lte(self, column: str, value):
        if not value:
            return self
        self._conditions.append((f"date({column})", "<=", value, "date(?)"))
        return self

    def json_like(self, column: str, value):
        if not value:
            return self
        self._conditions.append((column, "LIKE", f'%"{value}"%', None, True))
        return self

    def build_where(self) -> Tuple[str, List]:
        if not self._conditions:
            return "1=1", []
        parts = []
        params = []
        for cond in self._conditions:
            if len(cond) == 3:
                col, op, val = cond
                parts.append(f"{col} {op} ?")
                params.append(val)
            elif len(cond) == 4:
                col, op, val, placeholder = cond
                parts.append(f"{col} >= {placeholder}" if op == ">=" else f"{col} <= {placeholder}")
                params.append(val)
            elif len(cond) == 5:
                col, op, val, _, _ = cond
                parts.append(f"{col} {op} ?")
                params.append(val)
        return " AND ".join(parts), params

    def build_select(self, select_cols: str = "*", extra_where: str = "", extra_params: List = None) -> Tuple[str, List]:
        where_clause, params = self.build_where()
        sql = f"SELECT {select_cols} FROM {self._table} WHERE {where_clause}"
        if extra_where:
            sql += f" AND {extra_where}"
        if extra_params:
            params.extend(extra_params)
        return sql, params

    def build_count(self, extra_where: str = "", extra_params: List = None) -> Tuple[str, List]:
        where_clause, params = self.build_where()
        sql = f"SELECT COUNT(*) as cnt FROM {self._table} WHERE {where_clause}"
        if extra_where:
            sql += f" AND {extra_where}"
        if extra_params:
            params.extend(extra_params)
        return sql, params

    def build_paginated(
        self,
        select_cols: str = "*",
        page: int = 1,
        page_size: int = 20,
        order_by: str = "created_at DESC",
        extra_where: str = "",
        extra_params: List = None
    ) -> Tuple[str, List, str, List]:
        where_clause, params = self.build_where()
        base = f"SELECT {select_cols} FROM {self._table} WHERE {where_clause}"
        if extra_where:
            base += f" AND {extra_where}"
            if extra_params:
                params.extend(extra_params)

        count_sql = base.replace(f"SELECT {select_cols} FROM", "SELECT COUNT(*) as cnt FROM")
        count_sql = count_sql.split(" ORDER BY ")[0] if " ORDER BY " in count_sql else count_sql
        count_params = list(params)

        offset = (page - 1) * page_size
        data_sql = f"{base} ORDER BY {order_by} LIMIT ? OFFSET ?"
        data_params = params + [page_size, offset]

        return data_sql, data_params, count_sql, count_params


def paginate_result(conn, row_mapper, data_sql, data_params, count_sql, count_params, page, page_size):
    c = conn.cursor()
    c.execute(count_sql, count_params)
    total = c.fetchone()["cnt"] or 0
    c.execute(data_sql, data_params)
    items = [row_mapper(r) for r in c.fetchall()]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items
    }
