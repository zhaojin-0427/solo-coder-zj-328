from fastapi import APIRouter, HTTPException
from typing import Optional
from ..schemas import (
    UniformResponse, CodeEnum, VerifyRequest, VerifyResult,
    AgentRelation, MissingDetail
)
from ..database import Database
from ..rules import RuleEngine
from ..db_utils import ok

router = APIRouter(prefix="/api/verify", tags=["材料校验与缺件提示"])
_db: Optional[Database] = None
_engine: Optional[RuleEngine] = None


def set_db_and_engine(db: Database, engine: RuleEngine):
    global _db, _engine
    _db = db
    _engine = engine


@router.post("", response_model=UniformResponse, summary="提交材料进行校验")
def verify_materials(request: VerifyRequest):
    if request.is_agent and not request.agent_relation:
        raise HTTPException(status_code=400, detail="代办场景必须提供代办关系(agent_relation)")

    item = _db.get_item(request.item_code)
    if not item:
        raise HTTPException(status_code=404, detail=f"事项编码 {request.item_code} 不存在")
    if not item.enabled:
        raise HTTPException(status_code=400, detail=f"事项 {item.item_name} 已暂停办理")

    try:
        result: VerifyResult = _engine.validate_materials(
            item_code=request.item_code,
            elder_type=request.elder_type,
            is_agent=request.is_agent,
            agent_relation=request.agent_relation,
            submitted=request.submitted_materials
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    missing_categories = list(set([m.category.value for m in result.missing_list]))
    missing_details_list = [m.model_dump(mode="json") for m in result.missing_list]

    history_id = _db.save_verification(
        item_code=result.item_code,
        item_name=result.item_name,
        elder_type=request.elder_type.value,
        is_agent=request.is_agent,
        agent_relation=request.agent_relation.value if request.agent_relation else None,
        is_pass=result.is_pass,
        missing_count=result.total_missing,
        missing_categories=missing_categories,
        missing_details=missing_details_list
    )
    result.verification_id = history_id

    status_msg = "校验通过，材料齐全" if result.is_pass else f"校验未通过，缺件{result.total_missing}项"
    return ok(data=result.model_dump(mode="json"), message=status_msg)


@router.post("/relation", response_model=UniformResponse, summary="代办关系规则查询")
def check_agent_relation(relation: AgentRelation):
    rule_info = _engine.check_agent_relation(relation)
    return ok(data=rule_info, message=f"代办关系【{rule_info['label']}】校验规则")


@router.post("/makeup", response_model=UniformResponse, summary="记录材料补齐尝试")
def record_makeup(
    verification_id: int,
    missing_before: int,
    missing_after: int,
    attempt_no: int = 1
):
    detail = _db.get_history_detail(verification_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"校验记录ID {verification_id} 不存在")
    _db.record_make_up_attempt(
        verification_id=verification_id,
        item_code=detail["record"].item_code,
        attempt_no=attempt_no,
        missing_before=missing_before,
        missing_after=missing_after
    )
    return ok(message=f"已记录第{attempt_no}次补齐尝试（缺件从{missing_before}降至{missing_after}）")
