from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..schemas import (
    UniformResponse, CodeEnum,
    ExceptionCreateRequest, ExceptionStatusUpdateRequest,
    ExceptionAssignRequest, ExceptionProcessingRecordCreate,
    ExceptionCloseRequest, ExceptionType, ExceptionStatus,
    DisposalPriority, ServiceWindow
)
from ..database import Database

router = APIRouter(prefix="/api/exceptions", tags=["办事过程异常上报与闭环处置"])
_db: Optional[Database] = None


def set_db(db: Database):
    global _db
    _db = db


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


@router.post("", response_model=UniformResponse, summary="上报异常事件并自动生成处置单")
def create_exception(request: ExceptionCreateRequest):
    try:
        req_dict = request.model_dump()
        req_dict["exception_type"] = request.exception_type
        req_dict["source_type"] = request.source_type
        order = _db.create_exception(req_dict)
        return ok(
            data=order.model_dump(mode="json"),
            message=f"异常事件上报成功，处置单号：{order.exception_no}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list", response_model=UniformResponse, summary="异常处置单列表（按事项/社区/窗口/异常类型/责任人等筛选）")
def list_exceptions(
    item_code: Optional[str] = Query(None, description="办理事项编码"),
    community: Optional[str] = Query(None, description="所属社区"),
    expected_window: Optional[ServiceWindow] = Query(None, description="办理窗口"),
    exception_type: Optional[ExceptionType] = Query(None, description="异常类型"),
    responsible_person: Optional[str] = Query(None, description="责任人姓名"),
    status: Optional[ExceptionStatus] = Query(None, description="异常状态"),
    priority: Optional[DisposalPriority] = Query(None, description="处置优先级"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    elder_name: Optional[str] = Query(None, description="老人姓名（模糊搜索）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    result = _db.list_exceptions(
        item_code=item_code,
        community=community,
        expected_window=expected_window.value if expected_window else None,
        exception_type=exception_type.value if exception_type else None,
        responsible_person=responsible_person,
        status=status.value if status else None,
        priority=priority.value if priority else None,
        start_date=start_date,
        end_date=end_date,
        elder_name=elder_name,
        page=page,
        page_size=page_size
    )
    data = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [r.model_dump(mode="json") for r in result["items"]]
    }
    return ok(data=data, message=f"异常处置单列表，共{result['total']}条")


@router.get("/{exception_id}", response_model=UniformResponse, summary="获取异常详情（含来源信息、处理记录、状态流转历史）")
def get_exception_detail(exception_id: int):
    order = _db.get_exception(exception_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    source_info = _db._fetch_source_info(order.source_type, order.source_id)
    processing_records = _db.get_exception_processing_records(exception_id)
    status_history = _db.get_exception_status_history(exception_id)
    data = {
        "order": order.model_dump(mode="json"),
        "source_info": source_info,
        "processing_records": [r.model_dump(mode="json") for r in processing_records],
        "status_history": [r.model_dump(mode="json") for r in status_history]
    }
    return ok(data=data, message=f"异常 {exception_id} 详情")


@router.put("/{exception_id}/status", response_model=UniformResponse, summary="异常状态流转")
def update_exception_status(exception_id: int, request: ExceptionStatusUpdateRequest):
    existing = _db.get_exception(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    updated = _db.update_exception_status(
        exception_id=exception_id,
        status=request.status.value,
        operator=request.operator,
        remark=request.remark
    )
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message=f"异常状态已更新为 {request.status.value}"
    )


@router.post("/{exception_id}/assign", response_model=UniformResponse, summary="指派责任人")
def assign_exception(exception_id: int, request: ExceptionAssignRequest):
    existing = _db.get_exception(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    updated = _db.assign_exception(
        exception_id=exception_id,
        responsible_role=request.responsible_role.value if request.responsible_role else None,
        responsible_person=request.responsible_person,
        responsible_phone=request.responsible_phone,
        assigned_by=request.assigned_by,
        assign_remark=request.assign_remark
    )
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message=f"已指派责任人：{request.responsible_person}"
    )


@router.post("/{exception_id}/records", response_model=UniformResponse, summary="追加处理记录")
def add_processing_record(exception_id: int, request: ExceptionProcessingRecordCreate):
    existing = _db.get_exception(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    record = _db.add_processing_record(
        exception_id=exception_id,
        processor=request.processor,
        action=request.action,
        result=request.result,
        next_step=request.next_step,
        duration_minutes=request.duration_minutes or 0
    )
    return ok(
        data=record.model_dump(mode="json") if record else None,
        message="处理记录已追加"
    )


@router.get("/{exception_id}/records", response_model=UniformResponse, summary="获取异常处理记录列表")
def get_processing_records(exception_id: int):
    existing = _db.get_exception(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    records = _db.get_exception_processing_records(exception_id)
    data = {
        "exception_id": exception_id,
        "total": len(records),
        "items": [r.model_dump(mode="json") for r in records]
    }
    return ok(data=data, message=f"异常 {exception_id} 处理记录")


@router.get("/{exception_id}/history", response_model=UniformResponse, summary="获取异常状态流转历史")
def get_status_history(exception_id: int):
    existing = _db.get_exception(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    history = _db.get_exception_status_history(exception_id)
    data = {
        "exception_id": exception_id,
        "total": len(history),
        "items": [r.model_dump(mode="json") for r in history]
    }
    return ok(data=data, message=f"异常 {exception_id} 状态流转历史")


@router.post("/{exception_id}/close", response_model=UniformResponse, summary="关闭确认（含回访建议）")
def close_exception(exception_id: int, request: ExceptionCloseRequest):
    existing = _db.get_exception(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"异常ID {exception_id} 不存在")
    updated = _db.close_exception(
        exception_id=exception_id,
        closed_by=request.closed_by,
        close_remark=request.close_remark,
        is_resolved=request.is_resolved,
        follow_up_suggestion=request.follow_up_suggestion
    )
    result_msg = "已解决" if request.is_resolved else "未解决"
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message=f"异常已关闭，处理结果：{result_msg}"
    )
