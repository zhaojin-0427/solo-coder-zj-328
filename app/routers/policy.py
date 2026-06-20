from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..schemas import (
    UniformResponse, CodeEnum,
    PolicyChangeCreate, PolicyChangeUpdate, PolicyChangeStatus,
    PolicyRiskLevel, WarningStatus, WarningSourceType,
    PolicyWarningConfirmRequest, ServiceWindow, ElderType
)
from ..database import Database

router = APIRouter(prefix="/api/policy", tags=["政策变更订阅与影响预警"])
_db: Optional[Database] = None


def set_db(db: Database):
    global _db
    _db = db


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


@router.post("/changes", response_model=UniformResponse, summary="创建政策变更记录")
def create_policy_change(request: PolicyChangeCreate):
    try:
        policy = _db.create_policy_change(request.model_dump())
        return ok(
            data=policy.model_dump(mode="json"),
            message=f"政策变更创建成功，ID: {policy.id}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/changes/list", response_model=UniformResponse, summary="政策变更列表（按事项/窗口/风险等级/状态筛选）")
def list_policy_changes(
    item_code: Optional[str] = Query(None, description="适用事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="适用窗口"),
    risk_level: Optional[PolicyRiskLevel] = Query(None, description="风险等级"),
    status: Optional[PolicyChangeStatus] = Query(None, description="政策状态"),
    start_date: Optional[str] = Query(None, description="生效起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="生效结束日期 YYYY-MM-DD"),
    keyword: Optional[str] = Query(None, description="关键词搜索（标题/描述/来源）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    result = _db.list_policy_changes(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        risk_level=risk_level.value if risk_level else None,
        status=status.value if status else None,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        page=page,
        page_size=page_size
    )
    data = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [item.model_dump(mode="json") for item in result["items"]]
    }
    return ok(data=data, message=f"政策变更列表，共{result['total']}条")


@router.get("/changes/{policy_id}", response_model=UniformResponse, summary="获取政策变更详情（含影响概览）")
def get_policy_change_detail(policy_id: int):
    detail = _db.get_policy_change_detail(policy_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"政策变更ID {policy_id} 不存在")
    data = {
        "policy": detail["policy"].model_dump(mode="json"),
        "impact_summary": detail["impact_summary"],
        "warning_count": detail["warning_count"],
        "confirmed_warning_count": detail["confirmed_warning_count"]
    }
    return ok(data=data, message=f"政策变更 {policy_id} 详情")


@router.put("/changes/{policy_id}", response_model=UniformResponse, summary="更新政策变更信息")
def update_policy_change(policy_id: int, request: PolicyChangeUpdate):
    existing = _db.get_policy_change(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"政策变更ID {policy_id} 不存在")
    try:
        updated = _db.update_policy_change(policy_id, request.model_dump(exclude_none=True))
        return ok(
            data=updated.model_dump(mode="json") if updated else None,
            message="政策变更已更新"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/changes/{policy_id}/status", response_model=UniformResponse, summary="启停政策变更状态")
def update_policy_status(policy_id: int, status: PolicyChangeStatus):
    existing = _db.get_policy_change(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"政策变更ID {policy_id} 不存在")
    updated = _db.update_policy_change(policy_id, {"status": status})
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message=f"政策变更状态已更新为 {status.value}"
    )


@router.delete("/changes/{policy_id}", response_model=UniformResponse, summary="删除政策变更")
def delete_policy_change(policy_id: int):
    existing = _db.get_policy_change(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"政策变更ID {policy_id} 不存在")
    success = _db.delete_policy_change(policy_id)
    return ok(
        data={"deleted": success},
        message="政策变更已删除" if success else "删除失败"
    )


@router.post("/changes/{policy_id}/scan", response_model=UniformResponse, summary="扫描政策变更影响范围并生成预警")
def scan_policy_impact(policy_id: int):
    existing = _db.get_policy_change(policy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"政策变更ID {policy_id} 不存在")
    result = _db.scan_policy_impact(policy_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return ok(
        data=result,
        message=f"影响范围扫描完成，新增预警 {result['new_warnings_count']} 条"
    )


@router.get("/warnings/list", response_model=UniformResponse, summary="预警列表（按事项/窗口/社区/风险等级/状态筛选）")
def list_policy_warnings(
    policy_change_id: Optional[int] = Query(None, description="政策变更ID"),
    source_type: Optional[WarningSourceType] = Query(None, description="来源类型"),
    item_code: Optional[str] = Query(None, description="办理事项编码"),
    community: Optional[str] = Query(None, description="所属社区"),
    expected_window: Optional[ServiceWindow] = Query(None, description="办理窗口"),
    risk_level: Optional[PolicyRiskLevel] = Query(None, description="风险等级"),
    status: Optional[WarningStatus] = Query(None, description="预警状态"),
    elder_name: Optional[str] = Query(None, description="老人姓名（模糊搜索）"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    result = _db.list_policy_warnings(
        policy_change_id=policy_change_id,
        source_type=source_type.value if source_type else None,
        item_code=item_code,
        community=community,
        expected_window=expected_window.value if expected_window else None,
        risk_level=risk_level.value if risk_level else None,
        status=status.value if status else None,
        elder_name=elder_name,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size
    )
    data = {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [item.model_dump(mode="json") for item in result["items"]]
    }
    return ok(data=data, message=f"预警列表，共{result['total']}条")


@router.get("/warnings/{warning_id}", response_model=UniformResponse, summary="获取预警详情")
def get_policy_warning(warning_id: int):
    warning = _db.get_policy_warning(warning_id)
    if not warning:
        raise HTTPException(status_code=404, detail=f"预警ID {warning_id} 不存在")
    history = _db.get_policy_warning_history(warning_id)
    data = {
        "warning": warning.model_dump(mode="json"),
        "status_history": history
    }
    return ok(data=data, message=f"预警 {warning_id} 详情")


@router.post("/warnings/{warning_id}/confirm", response_model=UniformResponse, summary="确认预警")
def confirm_policy_warning(warning_id: int, request: PolicyWarningConfirmRequest):
    existing = _db.get_policy_warning(warning_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"预警ID {warning_id} 不存在")
    if existing.status == "confirmed":
        raise HTTPException(status_code=400, detail="该预警已确认，无需重复确认")
    updated = _db.confirm_policy_warning(
        warning_id=warning_id,
        confirmed_by=request.confirmed_by,
        confirm_remark=request.confirm_remark
    )
    return ok(
        data=updated.model_dump(mode="json") if updated else None,
        message="预警已确认"
    )


@router.get("/impact/query", response_model=UniformResponse, summary="查询政策影响（按老人身份/事项/社区/窗口/预约日期）")
def query_policy_impact(
    elder_type: Optional[ElderType] = Query(None, description="老人身份类型"),
    item_code: Optional[str] = Query(None, description="办理事项编码"),
    community: Optional[str] = Query(None, description="所属社区"),
    expected_window: Optional[ServiceWindow] = Query(None, description="办理窗口"),
    appointment_date: Optional[str] = Query(None, description="预约日期 YYYY-MM-DD")
):
    result = _db.query_policy_impact(
        elder_type=elder_type.value if elder_type else None,
        item_code=item_code,
        community=community,
        expected_window=expected_window.value if expected_window else None,
        appointment_date=appointment_date
    )
    msg = "该条件下的办事受政策变更影响" if result["is_affected"] else "该条件下的办事暂不受政策变更影响"
    return ok(data=result, message=msg)


@router.get("/stats/overall", response_model=UniformResponse, summary="政策变更综合统计")
def get_policy_stats_overall(
    item_code: Optional[str] = Query(None, description="指定事项编码，留空为全部"),
    community: Optional[str] = Query(None, description="指定社区，留空为全部"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口，留空为全部"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD")
):
    stats = _db.get_policy_stats(
        item_code=item_code,
        community=community,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    return ok(data=stats, message="政策变更综合统计数据")


@router.get("/stats/item-ranking", response_model=UniformResponse, summary="各事项政策影响排行")
def get_policy_item_ranking(
    community: Optional[str] = Query(None, description="指定社区"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(10, ge=1, le=50, description="返回TOP N")
):
    stats = _db.get_policy_stats(
        community=community,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    ranking = stats["item_policy_impact_ranking"][:limit]
    data = {
        "total_items": len(ranking),
        "ranking": ranking
    }
    return ok(data=data, message="各事项政策影响排行")


@router.get("/stats/warning-summary", response_model=UniformResponse, summary="预警统计概览")
def get_warning_summary(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    community: Optional[str] = Query(None, description="指定社区"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_policy_stats(
        item_code=item_code,
        community=community,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    confirm_rate = round(stats["confirmed_warnings"] / stats["total_warnings"], 4) if stats["total_warnings"] > 0 else 0.0
    interpretation = ""
    if stats["unconfirmed_high_risk_warnings"] > 0:
        interpretation = f"存在 {stats['unconfirmed_high_risk_warnings']} 条未确认的高风险预警，建议尽快处理。"
    elif stats["total_warnings"] == 0:
        interpretation = "暂无政策预警数据。"
    else:
        interpretation = f"预警确认率为 {round(confirm_rate * 100, 2)}%，整体处置情况良好。"

    data = {
        "total_warnings": stats["total_warnings"],
        "confirmed_warnings": stats["confirmed_warnings"],
        "unconfirmed_warnings": stats["total_warnings"] - stats["confirmed_warnings"],
        "unconfirmed_high_risk_warnings": stats["unconfirmed_high_risk_warnings"],
        "confirm_rate": confirm_rate,
        "confirm_rate_percent": f"{round(confirm_rate * 100, 2)}%",
        "interpretation": interpretation
    }
    return ok(data=data, message="预警统计概览")


@router.get("/stats/policy-exception-ratio", response_model=UniformResponse, summary="因政策变更导致的异常占比统计")
def get_policy_exception_ratio(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_policy_stats(
        item_code=item_code,
        start_date=start_date,
        end_date=end_date
    )
    ratio = stats["policy_exception_ratio"]
    interpretation = ""
    if ratio >= 0.2:
        interpretation = f"政策变更导致的异常占比偏高（{round(ratio * 100, 2)}%），建议加强政策变更前的宣传和告知工作。"
    elif ratio >= 0.1:
        interpretation = f"政策变更导致的异常占比中等（{round(ratio * 100, 2)}%），存在一定改进空间。"
    else:
        interpretation = f"政策变更导致的异常占比较低（{round(ratio * 100, 2)}%），整体运行良好。"

    data = {
        "total_exceptions": stats["total_exceptions"],
        "policy_exception_count": stats["policy_exception_count"],
        "policy_exception_ratio": ratio,
        "policy_exception_ratio_percent": f"{round(ratio * 100, 2)}%",
        "interpretation": interpretation
    }
    return ok(data=data, message="政策变更异常占比统计")
