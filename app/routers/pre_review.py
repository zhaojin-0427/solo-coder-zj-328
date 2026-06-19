from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import json

from ..schemas import (
    UniformResponse, CodeEnum, PreReviewSubmitRequest,
    PreReviewStatusUpdateRequest, SupplementReviewRequest,
    PreReviewStatus, ServiceWindow
)
from ..database import Database
from ..rules import RuleEngine
from ..pre_review_service import PreReviewService

router = APIRouter(prefix="/api/pre-review", tags=["窗口预审与一次性告知工单"])
_db: Optional[Database] = None
_engine: Optional[RuleEngine] = None
_service: Optional[PreReviewService] = None


def set_db_and_engine(db: Database, engine: RuleEngine):
    global _db, _engine, _service
    _db = db
    _engine = engine
    _service = PreReviewService(db, engine)


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


@router.post("", response_model=UniformResponse, summary="提交窗口预审，生成预审工单")
def submit_pre_review(request: PreReviewSubmitRequest):
    if request.is_agent and not request.agent_relation:
        raise HTTPException(status_code=400, detail="代办场景必须提供代办关系(agent_relation)")
    if request.is_agent and not request.agent_name:
        raise HTTPException(status_code=400, detail="代办场景必须提供代办人姓名(agent_name)")

    item = _db.get_item(request.item_code)
    if not item:
        raise HTTPException(status_code=404, detail=f"事项编码 {request.item_code} 不存在")
    if not item.enabled:
        raise HTTPException(status_code=400, detail=f"事项 {item.item_name} 已暂停办理")

    try:
        order, extra = _service.submit_pre_review(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预审处理失败: {str(e)}")

    data = {
        "work_order": order.model_dump(mode="json"),
        **extra
    }
    status_msg = "预审通过，材料齐全" if order.is_pass else (
        f"预审未通过，缺件{order.total_missing}项" + ("（重复预审，已关联历史工单）" if order.is_duplicate else "")
    )
    return ok(data=data, message=status_msg)


@router.get("/list", response_model=UniformResponse, summary="按条件筛选预审工单列表")
def list_pre_review_orders(
    item_code: Optional[str] = Query(None, description="事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="预计办理窗口"),
    status: Optional[PreReviewStatus] = Query(None, description="工单状态"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    elder_id_card: Optional[str] = Query(None, description="老人身份证号"),
    contact_phone: Optional[str] = Query(None, description="联系电话"),
    risk_level: Optional[str] = Query(None, description="风险等级 low/medium/high/critical"),
    is_duplicate: Optional[bool] = Query(None, description="是否重复预审"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    _db.mark_expired_orders()
    result = _db.list_pre_review_orders(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        status=status.value if status else None,
        start_date=start_date,
        end_date=end_date,
        elder_id_card=elder_id_card,
        contact_phone=contact_phone,
        risk_level=risk_level,
        is_duplicate=is_duplicate,
        page=page,
        page_size=page_size
    )
    data = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [o.model_dump(mode="json") for o in result["items"]]
    }
    return ok(data=data, message=f"预审工单列表，共{result['total']}条")


@router.get("/{order_id}", response_model=UniformResponse, summary="获取预审工单详情")
def get_pre_review_detail(order_id: int):
    _db.mark_expired_orders()
    detail = _service.get_order_detail(order_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"预审工单ID {order_id} 不存在")
    return ok(data=detail, message=f"预审工单 {order_id} 详情")


@router.get("/no/{work_order_no}", response_model=UniformResponse, summary="按工单号获取预审工单详情")
def get_pre_review_by_no(work_order_no: str):
    order = _db.get_pre_review_by_no(work_order_no)
    if not order:
        raise HTTPException(status_code=404, detail=f"预审工单号 {work_order_no} 不存在")
    detail = _service.get_order_detail(order.id)
    return ok(data=detail, message=f"预审工单 {work_order_no} 详情")


@router.put("/{order_id}/status", response_model=UniformResponse, summary="更新预审工单状态（状态流转）")
def update_pre_review_status(order_id: int, request: PreReviewStatusUpdateRequest):
    order = _db.get_pre_review_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"预审工单ID {order_id} 不存在")

    valid_transitions = {
        PreReviewStatus.PENDING: {PreReviewStatus.IN_REVIEW, PreReviewStatus.SUPPLEMENTING, PreReviewStatus.REJECTED, PreReviewStatus.EXPIRED},
        PreReviewStatus.IN_REVIEW: {PreReviewStatus.PASSED, PreReviewStatus.SUPPLEMENTING, PreReviewStatus.REJECTED, PreReviewStatus.COMPLETED},
        PreReviewStatus.SUPPLEMENTING: {PreReviewStatus.PASSED, PreReviewStatus.IN_REVIEW, PreReviewStatus.EXPIRED, PreReviewStatus.REJECTED},
        PreReviewStatus.PASSED: {PreReviewStatus.COMPLETED, PreReviewStatus.SUPPLEMENTING},
        PreReviewStatus.REJECTED: {PreReviewStatus.SUPPLEMENTING, PreReviewStatus.PENDING},
        PreReviewStatus.EXPIRED: {PreReviewStatus.PENDING, PreReviewStatus.SUPPLEMENTING},
        PreReviewStatus.COMPLETED: set(),
    }
    current_status = PreReviewStatus(order.status)
    target_status = request.status
    if target_status not in valid_transitions.get(current_status, set()):
        if current_status != target_status:
            raise HTTPException(
                status_code=400,
                detail=f"状态流转不合法: {current_status.value} 不能流转到 {target_status.value}"
            )

    updated = _db.update_pre_review_status(
        order_id=order_id,
        status=target_status.value,
        reviewer=request.reviewer,
        review_remark=request.review_remark
    )

    if request.reviewer and updated:
        _db.create_notice_record(
            work_order_id=updated.id,
            work_order_no=updated.work_order_no,
            notice_type="status_change",
            notice_content=(f"工单状态已变更为：{target_status.value}" + (f"，审核意见：{request.review_remark}" if request.review_remark else "")),
            notice_method="manual",
            notified_to=updated.agent_name or updated.elder_name,
            notified_phone=updated.contact_phone
        )

    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message=f"工单状态已更新为 {target_status.value}"
    )


@router.post("/supplement-review", response_model=UniformResponse, summary="补齐材料复核")
def supplement_review(request: SupplementReviewRequest):
    order = _db.get_pre_review_order(request.work_order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"预审工单ID {request.work_order_id} 不存在")
    if order.status == PreReviewStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="已完成的工单不可再复核")

    try:
        req_dict = request.model_dump(mode="json")
        result = _service.supplement_review(req_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"复核处理失败: {str(e)}")

    msg = "补齐复核通过，材料已齐全" if result["review_passed"] else (
        f"复核仍有缺件，缺件从{result['missing_before']}项降至{result['missing_after']}项"
    )
    return ok(data=result, message=msg)


@router.get("/{order_id}/supplement-history", response_model=UniformResponse, summary="查询工单补齐记录")
def get_supplement_history(order_id: int):
    order = _db.get_pre_review_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"预审工单ID {order_id} 不存在")
    records = _db.list_supplement_records(order_id)
    return ok(
        data={"order_id": order_id, "work_order_no": order.work_order_no, "records": records},
        message=f"补齐记录，共{len(records)}条"
    )


@router.get("/notices/list", response_model=UniformResponse, summary="查询一次性告知记录")
def list_notice_records(
    work_order_id: Optional[int] = Query(None, description="指定工单ID"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    notice_method: Optional[str] = Query(None, description="告知方式: system/manual"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    records = _db.list_notice_records(
        work_order_id=work_order_id,
        start_date=start_date,
        end_date=end_date,
        notice_method=notice_method,
        limit=limit,
        offset=offset
    )
    data = [r.model_dump(mode="json") for r in records]
    return ok(data={"total": len(data), "records": data}, message=f"一次性告知记录，共{len(data)}条")


@router.get("/{order_id}/notices", response_model=UniformResponse, summary="查询指定工单的所有告知记录")
def get_order_notices(order_id: int):
    order = _db.get_pre_review_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"预审工单ID {order_id} 不存在")
    records = _db.list_notice_records(work_order_id=order_id)
    data = [r.model_dump(mode="json") for r in records]
    return ok(
        data={"order_id": order_id, "work_order_no": order.work_order_no, "total": len(data), "records": data},
        message=f"工单告知记录，共{len(data)}条"
    )


@router.get("/duplicate/check", response_model=UniformResponse, summary="检查是否为重复预审")
def check_duplicate(
    item_code: str,
    elder_id_card: Optional[str] = None,
    contact_phone: Optional[str] = None,
    days: int = Query(7, ge=1, le=30, description="重复判定天数")
):
    if not elder_id_card and not contact_phone:
        raise HTTPException(status_code=400, detail="必须至少提供 elder_id_card 或 contact_phone 之一")
    duplicates = _db.find_duplicate_orders(
        item_code=item_code,
        elder_id_card=elder_id_card,
        contact_phone=contact_phone,
        days=days
    )
    data = {
        "is_duplicate": len(duplicates) > 0,
        "duplicate_count": len(duplicates),
        "duplicates": [
            {
                "id": d.id,
                "work_order_no": d.work_order_no,
                "elder_name": d.elder_name,
                "status": d.status,
                "total_missing": d.total_missing,
                "created_at": d.created_at.isoformat()
            }
            for d in duplicates
        ]
    }
    msg = f"检测到{len(duplicates)}条重复预审记录" if duplicates else "在{days}天内未发现重复预审"
    return ok(data=data, message=msg.format(days=days))
