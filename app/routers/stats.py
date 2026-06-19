from fastapi import APIRouter, Query
from typing import Optional
from ..schemas import UniformResponse, CodeEnum, ServiceWindow
from ..database import Database

router = APIRouter(prefix="/api/stats", tags=["统计分析"])
_db: Optional[Database] = None


def set_db(db: Database):
    global _db
    _db = db


def ok(data=None, message="success") -> UniformResponse:
    return UniformResponse(code=CodeEnum.SUCCESS, message=message, data=data)


@router.get("/overall", response_model=UniformResponse, summary="综合统计看板")
def get_overall_stats(
    item_code: Optional[str] = Query(None, description="指定事项统计，留空为全部"),
    limit_items: int = Query(10, ge=1, le=50, description="高频缺件事项TOP N"),
    limit_materials: int = Query(10, ge=1, le=50, description="高频错误材料TOP N")
):
    stats = _db.get_overall_stats(item_code=item_code, limit_items=limit_items, limit_materials=limit_materials)
    return ok(data=stats.model_dump(mode="json"), message="综合统计数据")


@router.get("/miss-rate", response_model=UniformResponse, summary="各事项缺件率排行")
def get_item_miss_rate(
    limit: int = Query(20, ge=1, le=100, description="返回数量")
):
    stats = _db.get_overall_stats(limit_items=limit, limit_materials=0)
    data = {
        "total_queries": stats.total_queries,
        "overall_miss_rate": stats.overall_miss_rate,
        "items": [s.model_dump(mode="json") for s in stats.top_items]
    }
    return ok(data=data, message="事项缺件率排行")


@router.get("/top-materials", response_model=UniformResponse, summary="高频错误材料排行")
def get_top_error_materials(
    limit: int = Query(20, ge=1, le=100, description="返回数量")
):
    stats = _db.get_overall_stats(limit_items=0, limit_materials=limit)
    data = {
        "total_miss_count": sum(m.miss_count for m in stats.top_materials),
        "materials": [m.model_dump(mode="json") for m in stats.top_materials]
    }
    return ok(data=data, message="高频错误材料排行")


@router.get("/agent-distribution", response_model=UniformResponse, summary="代办场景分布统计")
def get_agent_distribution():
    stats = _db.get_overall_stats(limit_items=0, limit_materials=0)
    data = {
        "total_agent_queries": sum(a.count for a in stats.agent_distribution),
        "distribution": [a.model_dump(mode="json") for a in stats.agent_distribution]
    }
    return ok(data=data, message="代办场景分布统计")


@router.get("/makeup-summary", response_model=UniformResponse, summary="材料补齐次数统计")
def get_makeup_summary():
    stats = _db.get_overall_stats(limit_items=0, limit_materials=0)
    data = {
        "avg_make_up_count": stats.avg_make_up_count,
        "total_queries": stats.total_queries,
        "interpretation": (
            "平均每位老人需要 {:.2f} 次材料补充才能办完事。".format(stats.avg_make_up_count)
            + (" 建议加强一次性告知工作。" if stats.avg_make_up_count >= 1.5 else " 告知效果良好。")
        )
    }
    return ok(data=data, message="材料补齐次数统计")


@router.get("/pre-review/overall", response_model=UniformResponse, summary="窗口预审综合统计")
def get_pre_review_overall(
    item_code: Optional[str] = Query(None, description="指定事项编码，留空为全部"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口，留空为全部"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD")
):
    stats = _db.get_pre_review_stats(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    return ok(data=stats, message="窗口预审综合统计数据")


@router.get("/pre-review/pass-rate", response_model=UniformResponse, summary="窗口预审通过率统计")
def get_pre_review_pass_rate(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_pre_review_stats(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    data = {
        "total_orders": stats["total_orders"],
        "pass_count": stats["pass_count"],
        "pass_rate": stats["pass_rate"],
        "pass_rate_percent": f"{round(stats['pass_rate'] * 100, 2)}%",
        "expired_count": stats["expired_count"],
        "supplement_in_progress_count": stats["supplement_in_progress_count"],
        "window_pass_rates": stats["window_pass_rates"]
    }
    return ok(data=data, message="窗口预审通过率统计")


@router.get("/pre-review/duplicate-rate", response_model=UniformResponse, summary="重复预审率统计")
def get_pre_review_duplicate_rate(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_pre_review_stats(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    interpretation = ""
    dup_rate = stats["duplicate_rate"]
    if dup_rate >= 0.3:
        interpretation = "重复预审率偏高（{:.1f}%），建议加强预审材料准备的告知宣传，减少老人重复跑腿。".format(dup_rate * 100)
    elif dup_rate >= 0.15:
        interpretation = "重复预审率中等（{:.1f}%），存在一定重复提交现象。".format(dup_rate * 100)
    else:
        interpretation = "重复预审率较低（{:.1f}%），一次性告知效果良好。".format(dup_rate * 100)
    data = {
        "total_orders": stats["total_orders"],
        "duplicate_count": stats["duplicate_count"],
        "duplicate_rate": stats["duplicate_rate"],
        "duplicate_rate_percent": f"{round(dup_rate * 100, 2)}%",
        "interpretation": interpretation
    }
    return ok(data=data, message="重复预审率统计")


@router.get("/pre-review/item-avg-missing", response_model=UniformResponse, summary="各事项平均缺件数统计")
def get_item_avg_missing(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_pre_review_stats(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    data = {
        "overall_avg_missing_count": stats["avg_missing_count"],
        "item_avg_missing": stats["item_avg_missing"]
    }
    return ok(data=data, message="各事项平均缺件数统计")


@router.get("/pre-review/expired-summary", response_model=UniformResponse, summary="超期未补齐工单统计")
def get_expired_summary(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期")
):
    stats = _db.get_pre_review_stats(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    expired_rate = round(stats["expired_count"] / stats["total_orders"], 4) if stats["total_orders"] > 0 else 0.0
    data = {
        "total_orders": stats["total_orders"],
        "expired_count": stats["expired_count"],
        "expired_rate": expired_rate,
        "expired_rate_percent": f"{round(expired_rate * 100, 2)}%",
        "supplement_in_progress_count": stats["supplement_in_progress_count"],
        "interpretation": (
            f"超期工单共{stats['expired_count']}张，建议对临近超期的工单进行短信或电话提醒。"
            f" 当前有{stats['supplement_in_progress_count']}张工单处于补齐流程中。"
        )
    }
    return ok(data=data, message="超期未补齐工单统计")


@router.get("/pre-review/top-return-material-combos", response_model=UniformResponse, summary="最常导致退回的材料组合排行")
def get_top_return_material_combos(
    item_code: Optional[str] = Query(None, description="指定事项编码"),
    expected_window: Optional[ServiceWindow] = Query(None, description="指定窗口"),
    start_date: Optional[str] = Query(None, description="起始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(10, ge=1, le=30, description="返回TOP N")
):
    stats = _db.get_pre_review_stats(
        item_code=item_code,
        expected_window=expected_window.value if expected_window else None,
        start_date=start_date,
        end_date=end_date
    )
    top_combos = stats["top_return_material_combos"][:limit]
    total_return = sum(c["combo_count"] for c in top_combos)
    data = {
        "total_return_with_combo": total_return,
        "top_combos": top_combos,
        "interpretation": (
            f"前{len(top_combos)}组材料组合共导致{total_return}次预审退回，"
            + ("建议重点加强这些材料组合的一次性告知工作。" if top_combos else "暂无退回数据。")
        )
    }
    return ok(data=data, message="最常导致退回的材料组合排行")
