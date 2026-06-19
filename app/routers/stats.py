from fastapi import APIRouter, Query
from typing import Optional
from ..schemas import UniformResponse, CodeEnum
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
