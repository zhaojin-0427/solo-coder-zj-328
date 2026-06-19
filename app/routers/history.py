from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..schemas import UniformResponse, CodeEnum
from ..database import Database

router = APIRouter(prefix="/api/history", tags=["历史查询"])
_db: Optional[Database] = None


def set_db(db: Database):
    global _db
    _db = db


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


@router.get("", response_model=UniformResponse, summary="分页查询校验历史")
def list_history(
    item_code: Optional[str] = Query(None, description="事项编码过滤"),
    is_pass: Optional[bool] = Query(None, description="是否通过过滤"),
    is_agent: Optional[bool] = Query(None, description="是否代办过滤"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    records = _db.list_history(
        item_code=item_code,
        is_pass=is_pass,
        is_agent=is_agent,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    return ok(data=[r.model_dump(mode="json") for r in records])


@router.get("/{history_id}", response_model=UniformResponse, summary="查询单条历史详情（含缺件明细）")
def get_history_detail(history_id: int):
    detail = _db.get_history_detail(history_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"历史记录ID {history_id} 不存在")
    data = {
        "record": detail["record"].model_dump(mode="json"),
        "missing_details": detail["missing_details"]
    }
    return ok(data=data)
