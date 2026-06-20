from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..schemas import (
    UniformResponse, CodeEnum,
    CompanionResourceCreate, CompanionResourceUpdate, CompanionType,
    AccompanyAppointmentCreate, AccompanyAppointmentReassign,
    AccompanyStatusUpdate, AccompanyCancelRequest,
    AccompanyFollowUpCreate, AppointmentStatus, ServiceWindow
)
from ..database import Database
from ..db_utils import ok

router = APIRouter(prefix="/api/accompany", tags=["长者办事陪同资源匹配与预约派单"])
_db: Optional[Database] = None


def set_db(db: Database):
    global _db
    _db = db


# ========== 陪同资源配置 ==========

@router.post("/companions", response_model=UniformResponse, summary="新增陪同资源（志愿者/社工/家属联系人）")
def create_companion_resource(request: CompanionResourceCreate):
    resource = _db.create_companion_resource(request)
    return ok(
        data=resource.model_dump(mode="json"),
        message=f"陪同资源 {resource.name} 创建成功"
    )


@router.get("/companions/list", response_model=UniformResponse, summary="陪同资源列表（支持按社区/类型/状态筛选）")
def list_companion_resources(
    community: Optional[str] = Query(None, description="所属社区"),
    companion_type: Optional[CompanionType] = Query(None, description="陪同人类型"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    result = _db.list_companion_resources(
        community=community,
        companion_type=companion_type.value if companion_type else None,
        is_active=is_active,
        page=page,
        page_size=page_size
    )
    data = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [r.model_dump(mode="json") for r in result["items"]]
    }
    return ok(data=data, message=f"陪同资源列表，共{result['total']}条")


@router.get("/companions/{resource_id}", response_model=UniformResponse, summary="获取陪同资源详情")
def get_companion_resource(resource_id: int):
    resource = _db.get_companion_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail=f"陪同资源ID {resource_id} 不存在")
    return ok(data=resource.model_dump(mode="json"), message=f"陪同资源 {resource_id} 详情")


@router.put("/companions/{resource_id}", response_model=UniformResponse, summary="更新陪同资源信息")
def update_companion_resource(resource_id: int, request: CompanionResourceUpdate):
    existing = _db.get_companion_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同资源ID {resource_id} 不存在")
    updated = _db.update_companion_resource(resource_id, request)
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message="陪同资源信息已更新"
    )


@router.delete("/companions/{resource_id}", response_model=UniformResponse, summary="删除陪同资源")
def delete_companion_resource(resource_id: int):
    existing = _db.get_companion_resource(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同资源ID {resource_id} 不存在")
    deleted = _db.delete_companion_resource(resource_id)
    return ok(data={"deleted": deleted}, message="陪同资源已删除" if deleted else "删除失败")


# ========== 陪同预约单 ==========

@router.post("/appointments", response_model=UniformResponse, summary="创建陪同预约（自动匹配陪同人）")
def create_accompany_appointment(request: AccompanyAppointmentCreate):
    try:
        req_dict = request.model_dump()
        req_dict["elder_type"] = request.elder_type
        req_dict["mobility_level"] = request.mobility_level
        req_dict["accompany_demand_type"] = request.accompany_demand_type
        req_dict["expected_window"] = request.expected_window
        result = _db.create_accompany_appointment(req_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预约创建失败: {str(e)}")
    appointment = result["appointment"]
    candidates = [c.model_dump(mode="json") for c in result["matched_candidates"]]
    data = {
        "appointment": appointment.model_dump(mode="json"),
        "matched_candidates": candidates
    }
    msg = f"预约创建成功，已匹配{len(candidates)}名陪同人，推荐：{appointment.recommended_companion_name or '暂无（待人工派单）'}"
    return ok(data=data, message=msg)


@router.get("/appointments/list", response_model=UniformResponse, summary="按社区/事项/日期/陪同人筛选预约列表")
def list_accompany_appointments(
    community: Optional[str] = Query(None, description="所在社区"),
    item_code: Optional[str] = Query(None, description="办理事项编码"),
    status: Optional[AppointmentStatus] = Query(None, description="预约状态"),
    start_date: Optional[str] = Query(None, description="创建起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="创建结束日期 YYYY-MM-DD"),
    expected_date: Optional[str] = Query(None, description="期望办理日期 YYYY-MM-DD"),
    recommended_companion_id: Optional[int] = Query(None, description="指定陪同人ID"),
    risk_level: Optional[str] = Query(None, description="风险等级 low/medium/high/critical"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    result = _db.list_accompany_appointments(
        community=community,
        item_code=item_code,
        status=status.value if status else None,
        start_date=start_date,
        end_date=end_date,
        expected_date=expected_date,
        recommended_companion_id=recommended_companion_id,
        risk_level=risk_level,
        page=page,
        page_size=page_size
    )
    data = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [a.model_dump(mode="json") for a in result["items"]]
    }
    return ok(data=data, message=f"陪同预约列表，共{result['total']}条")


@router.get("/appointments/{appointment_id}", response_model=UniformResponse, summary="获取陪同预约详情")
def get_accompany_appointment_detail(appointment_id: int):
    appointment = _db.get_accompany_appointment(appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail=f"陪同预约ID {appointment_id} 不存在")
    candidates = _db.get_match_candidates(appointment_id)
    service_history = _db.get_appointment_status_history(appointment_id)
    related_pr = None
    if appointment.pre_review_order_id:
        pr = _db.get_pre_review_order(appointment.pre_review_order_id)
        if pr:
            related_pr = pr.model_dump(mode="json")
    data = {
        "appointment": appointment.model_dump(mode="json"),
        "matched_candidates": [c.model_dump(mode="json") for c in candidates],
        "related_pre_review_order": related_pr,
        "service_history": service_history
    }
    return ok(data=data, message=f"陪同预约 {appointment_id} 详情")


@router.get("/appointments/no/{appointment_no}", response_model=UniformResponse, summary="按预约单号获取详情")
def get_accompany_appointment_by_no(appointment_no: str):
    appointment = _db.get_accompany_appointment_by_no(appointment_no)
    if not appointment:
        raise HTTPException(status_code=404, detail=f"预约单号 {appointment_no} 不存在")
    return get_accompany_appointment_detail(appointment.id)


@router.put("/appointments/{appointment_id}/reassign", response_model=UniformResponse, summary="预约改派（更换陪同人）")
def reassign_appointment(appointment_id: int, request: AccompanyAppointmentReassign):
    existing = _db.get_accompany_appointment(appointment_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同预约ID {appointment_id} 不存在")
    if existing.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"预约状态为 {existing.status}，不可改派")
    try:
        updated = _db.reassign_appointment(
            appointment_id=appointment_id,
            new_companion_id=request.new_companion_id,
            reassign_reason=request.reassign_reason,
            operator=request.operator
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message="预约改派成功"
    )


@router.put("/appointments/{appointment_id}/status", response_model=UniformResponse, summary="预约状态流转")
def update_accompany_status(appointment_id: int, request: AccompanyStatusUpdate):
    existing = _db.get_accompany_appointment(appointment_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同预约ID {appointment_id} 不存在")
    valid_transitions = {
        AppointmentStatus.PENDING_MATCH: {AppointmentStatus.MATCHED, AppointmentStatus.CANCELLED},
        AppointmentStatus.MATCHED: {AppointmentStatus.CONFIRMED, AppointmentStatus.REASSIGNED, AppointmentStatus.CANCELLED, AppointmentStatus.IN_SERVICE},
        AppointmentStatus.CONFIRMED: {AppointmentStatus.IN_SERVICE, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW, AppointmentStatus.REASSIGNED},
        AppointmentStatus.IN_SERVICE: {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW},
        AppointmentStatus.REASSIGNED: {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED, AppointmentStatus.IN_SERVICE},
        AppointmentStatus.COMPLETED: set(),
        AppointmentStatus.NO_SHOW: set(),
        AppointmentStatus.CANCELLED: set(),
    }
    current_status = AppointmentStatus(existing.status)
    target_status = request.status
    if target_status not in valid_transitions.get(current_status, set()):
        if current_status != target_status:
            raise HTTPException(
                status_code=400,
                detail=f"状态流转不合法: {current_status.value} 不能流转到 {target_status.value}"
            )
    updated = _db.update_accompany_status(
        appointment_id=appointment_id,
        status=target_status.value,
        operator=request.operator,
        remark=request.remark
    )
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message=f"预约状态已更新为 {target_status.value}"
    )


@router.post("/appointments/{appointment_id}/cancel", response_model=UniformResponse, summary="取消预约并记录取消原因")
def cancel_appointment(appointment_id: int, request: AccompanyCancelRequest):
    existing = _db.get_accompany_appointment(appointment_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同预约ID {appointment_id} 不存在")
    if existing.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"预约状态为 {existing.status}，不可取消")
    updated = _db.cancel_appointment(
        appointment_id=appointment_id,
        cancel_reason=request.cancel_reason,
        cancel_remark=request.cancel_remark,
        operator=request.operator
    )
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message="预约已取消"
    )


@router.get("/appointments/{appointment_id}/status-history", response_model=UniformResponse, summary="查询预约状态流转历史")
def get_appointment_status_history(appointment_id: int):
    existing = _db.get_accompany_appointment(appointment_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同预约ID {appointment_id} 不存在")
    history = _db.get_appointment_status_history(appointment_id)
    return ok(
        data={"appointment_id": appointment_id, "appointment_no": existing.appointment_no, "records": history},
        message=f"状态流转历史，共{len(history)}条"
    )


# ========== 陪同回访 ==========

@router.post("/follow-ups", response_model=UniformResponse, summary="提交陪同完成回访记录")
def create_follow_up(request: AccompanyFollowUpCreate):
    try:
        record = _db.create_follow_up(request.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回访记录提交失败: {str(e)}")
    return ok(
        data=record.model_dump(mode="json"),
        message="回访记录已提交"
    )


@router.get("/follow-ups/appointment/{appointment_id}", response_model=UniformResponse, summary="查询指定预约的回访记录")
def get_follow_ups_by_appointment(appointment_id: int):
    existing = _db.get_accompany_appointment(appointment_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"陪同预约ID {appointment_id} 不存在")
    records = _db.get_follow_ups_by_appointment(appointment_id)
    data = {
        "appointment_id": appointment_id,
        "appointment_no": existing.appointment_no,
        "total": len(records),
        "records": [r.model_dump(mode="json") for r in records]
    }
    return ok(data=data, message=f"回访记录，共{len(records)}条")


# ========== 统计分析 ==========

@router.get("/stats/overall", response_model=UniformResponse, summary="陪同服务综合统计")
def get_accompany_stats_overall(
    community: Optional[str] = Query(None, description="指定社区，留空为全部"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD")
):
    stats = _db.get_accompany_stats(
        community=community,
        start_date=start_date,
        end_date=end_date
    )
    return ok(data=stats, message="陪同服务综合统计数据")


@router.get("/stats/community", response_model=UniformResponse, summary="各社区预约量与完成率统计")
def get_community_stats(
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_accompany_stats(start_date=start_date, end_date=end_date)
    data = {
        "total_appointments": stats["total_appointments"],
        "overall_completion_rate": stats["completion_rate"],
        "community_stats": stats["community_stats"]
    }
    return ok(data=data, message="各社区预约量与完成率统计")


@router.get("/stats/risk-coverage", response_model=UniformResponse, summary="高风险老人陪同覆盖率统计")
def get_risk_coverage_stats(
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_accompany_stats(start_date=start_date, end_date=end_date)
    data = {
        "risk_coverage_stats": stats["risk_coverage_stats"]
    }
    return ok(data=data, message="高风险老人陪同覆盖率统计")


@router.get("/stats/companion-workload", response_model=UniformResponse, summary="陪同人工作量排行")
def get_companion_workload_ranking(
    community: Optional[str] = Query(None, description="指定社区"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_accompany_stats(
        community=community,
        start_date=start_date,
        end_date=end_date
    )
    data = {
        "companion_workload_ranking": stats["companion_workload_ranking"]
    }
    return ok(data=data, message="陪同人工作量排行")


@router.get("/stats/material-failures", response_model=UniformResponse, summary="材料未带齐导致的陪同失败原因排行")
def get_material_failure_ranking(
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_accompany_stats(start_date=start_date, end_date=end_date)
    data = {
        "material_failure_ranking": stats["material_failure_ranking"]
    }
    return ok(data=data, message="材料未带齐导致的陪同失败原因排行")
