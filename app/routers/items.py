from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from ..schemas import (
    UniformResponse, CodeEnum, ServiceItemCreate, ServiceItemUpdate, ServiceItem
)
from ..database import Database

router = APIRouter(prefix="/api/items", tags=["事项配置管理"])
_db: Optional[Database] = None


def set_db(db: Database):
    global _db
    _db = db


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


@router.get("", response_model=UniformResponse, summary="查询所有事项配置")
def list_items(
    enabled_only: bool = Query(False, description="仅查询已启用的事项")
):
    items = _db.list_items(enabled_only=enabled_only)
    return ok(data=[item.model_dump(mode="json") for item in items])


@router.get("/{item_code}", response_model=UniformResponse, summary="查询单个事项配置")
def get_item(item_code: str):
    item = _db.get_item(item_code)
    if not item:
        raise HTTPException(status_code=404, detail=f"事项编码 {item_code} 不存在")
    return ok(data=item.model_dump(mode="json"))


@router.post("", response_model=UniformResponse, summary="新增事项配置")
def create_item(data: ServiceItemCreate):
    existing = _db.get_item(data.item_code)
    if existing:
        raise HTTPException(status_code=400, detail=f"事项编码 {data.item_code} 已存在")
    item = _db.create_item(data)
    return ok(data=item.model_dump(mode="json"), message="事项创建成功")


@router.put("/{item_code}", response_model=UniformResponse, summary="更新事项配置")
def update_item(item_code: str, data: ServiceItemUpdate):
    item = _db.update_item(item_code, data)
    if not item:
        raise HTTPException(status_code=404, detail=f"事项编码 {item_code} 不存在")
    return ok(data=item.model_dump(mode="json"), message="事项更新成功")


@router.delete("/{item_code}", response_model=UniformResponse, summary="删除事项配置")
def delete_item(item_code: str):
    ok_flag = _db.delete_item(item_code)
    if not ok_flag:
        raise HTTPException(status_code=404, detail=f"事项编码 {item_code} 不存在")
    return ok(message="事项删除成功")
