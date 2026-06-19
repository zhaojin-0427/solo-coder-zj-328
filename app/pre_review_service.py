from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import json

from .schemas import (
    PreReviewSubmitRequest, PreReviewStatus, RiskLevel, ServiceWindow,
    ElderType, AgentRelation, MaterialCategory, VerifyResult, MissingDetail,
    SubmittedMaterial, MaterialSpec, PrintableCheckSummary, MaterialCheckSummaryItem
)
from .rules import RuleEngine, MATERIAL_LABELS, AGENT_RELATION_RULES, ELDER_TYPE_LABELS, PHOTO_SPEC_LABELS
from .database import Database


RISK_LABELS = {
    RiskLevel.LOW: "低风险",
    RiskLevel.MEDIUM: "中风险",
    RiskLevel.HIGH: "高风险",
    RiskLevel.CRITICAL: "极高风险",
}

WINDOW_LABELS = {
    ServiceWindow.MEDICAL_WINDOW: "医保业务窗口",
    ServiceWindow.SOCIAL_SECURITY_WINDOW: "社保业务窗口",
    ServiceWindow.BANKING_WINDOW: "银行业务窗口",
    ServiceWindow.CIVIL_AFFAIRS_WINDOW: "民政事务窗口",
    ServiceWindow.COMPREHENSIVE_WINDOW: "综合业务窗口",
    ServiceWindow.REGISTRATION_WINDOW: "登记业务窗口",
}


DEFAULT_WINDOW_MAP: Dict[str, ServiceWindow] = {
    "MEDICAL_REIMBURSEMENT": ServiceWindow.MEDICAL_WINDOW,
    "SOCIAL_SECURITY_VERIFY": ServiceWindow.SOCIAL_SECURITY_WINDOW,
    "BANK_CARD_REPORT_LOSS": ServiceWindow.BANKING_WINDOW,
    "HOSPITAL_REGISTRATION": ServiceWindow.REGISTRATION_WINDOW,
}


WINDOW_NOTES_TEMPLATES: Dict[ServiceWindow, List[str]] = {
    ServiceWindow.MEDICAL_WINDOW: [
        "请提前在叫号机取号，医保窗口一般在2-4号窗口",
        "如涉及跨院报销，需提前确认医院是否为医保定点单位",
        "费用发票需保留完整，破损或涂改的发票无法报销",
    ],
    ServiceWindow.SOCIAL_SECURITY_WINDOW: [
        "社保认证窗口支持人脸识别，请摘下口罩和帽子配合采集",
        "首次办理需先到取号机打印凭条，等待叫号",
        "如领取养老金银行卡有变更，请携带新卡一并办理",
    ],
    ServiceWindow.BANKING_WINDOW: [
        "挂失业务可先致电银行客服办理口头挂失，再到窗口正式挂失",
        "大额存款挂失需本人到场，代办需提前电话咨询银行政策",
        "建议取号前先在咨询台确认需要填写的表格",
    ],
    ServiceWindow.CIVIL_AFFAIRS_WINDOW: [
        "低保、高龄补贴等事项请每月15日前办理，避免月底系统结算",
        "涉及身份变更的事项，请先到户籍地派出所更新户籍信息",
    ],
    ServiceWindow.COMPREHENSIVE_WINDOW: [
        "综合窗口可受理多种事项，建议提前电话咨询确认",
        "首次办理可先到导办台取号并领取办事指南",
    ],
    ServiceWindow.REGISTRATION_WINDOW: [
        "住院登记窗口24小时开放，急诊可优先办理",
        "如有医保，请务必在入院48小时内完成医保登记",
        "预交金可通过微信、支付宝或银行卡缴纳",
    ],
}


def _assess_risk(
    verify_result: VerifyResult,
    is_agent: bool,
    agent_relation: Optional[AgentRelation],
    elder_type: ElderType,
    expected_window: Optional[ServiceWindow]
) -> RiskLevel:
    score = 0
    missing_count = verify_result.total_missing
    if missing_count == 0:
        score += 0
    elif missing_count <= 2:
        score += 1
    elif missing_count <= 5:
        score += 2
    else:
        score += 3

    if is_agent:
        if agent_relation in AGENT_RELATION_RULES:
            priority = AGENT_RELATION_RULES[agent_relation].get("priority_level", "medium")
            if priority == "low":
                score += 2
            elif priority == "medium":
                score += 1
        else:
            score += 2
        score += 1

    if elder_type in (ElderType.SPECIAL_ELDER, ElderType.DISABLED, ElderType.LOW_INCOME):
        score += 1

    high_risk_categories = {
        MaterialCategory.AUTHORIZATION_LETTER,
        MaterialCategory.HOSPITAL_CERT,
        MaterialCategory.DISABILITY_CERT,
        MaterialCategory.INCOME_PROOF,
    }
    missing_cats = set()
    for m in verify_result.missing_list:
        missing_cats.add(m.category)
    if high_risk_categories & missing_cats:
        score += 1

    if expected_window == ServiceWindow.BANKING_WINDOW:
        score += 1

    if score <= 1:
        return RiskLevel.LOW
    elif score <= 3:
        return RiskLevel.MEDIUM
    elif score <= 5:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def _generate_one_time_notice(
    item_name: str,
    elder_name: str,
    risk_level: RiskLevel,
    verify_result: VerifyResult,
    deadline: datetime,
    expected_window: Optional[ServiceWindow]
) -> str:
    lines = []
    lines.append(f"【一次性告知书】{item_name}预审结果告知")
    lines.append(f"尊敬的 {elder_name} 老人/家属：")
    lines.append("")
    risk_label = RISK_LABELS.get(risk_level, "未知")
    if verify_result.is_pass:
        lines.append(f"您提交的材料预审结果为：✅ 通过（风险等级：{risk_label}）。")
        lines.append("全部必选材料已准备齐全，可按预约时间前往窗口办理。")
    else:
        lines.append(f"您提交的材料预审结果为：⚠️ 需补齐（风险等级：{risk_label}）。")
        lines.append(f"共发现 {verify_result.total_missing} 项缺件/问题，请对照以下清单补齐：")
        lines.append("")
        for idx, m in enumerate(verify_result.missing_list, 1):
            lines.append(f"  {idx}. 【{MATERIAL_LABELS.get(m.category, m.category.value)}】{m.name}")
            lines.append(f"     ▸ 问题：{m.missing_type}")
            lines.append(f"     ▸ 建议：{m.suggestion}")
            lines.append("")

    if verify_result.special_notices:
        lines.append("【重要提醒】")
        for n in verify_result.special_notices:
            lines.append(f"  • {n}")
        lines.append("")

    if verify_result.supplement_notes:
        lines.append("【温馨提示】")
        for n in verify_result.supplement_notes:
            lines.append(f"  • {n}")
        lines.append("")

    if expected_window:
        win_label = WINDOW_LABELS.get(expected_window, expected_window.value)
        lines.append(f"【办理窗口】{win_label}")

    lines.append(f"【建议补齐截止时间】{deadline.strftime('%Y年%m月%d日 %H:%M')}")
    lines.append("请在截止时间前完成材料补齐，超期工单将自动标记为已过期。")
    lines.append("")
    lines.append("本告知书已通过系统自动生成，请妥善保存。如有疑问，可拨打服务热线咨询。")
    lines.append(f"告知时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")

    return "\n".join(lines)


def _generate_window_notes(
    expected_window: Optional[ServiceWindow],
    item_name: str,
    risk_level: RiskLevel
) -> List[str]:
    notes = []
    if expected_window and expected_window in WINDOW_NOTES_TEMPLATES:
        notes.extend(WINDOW_NOTES_TEMPLATES[expected_window])
    else:
        notes.append("请前往办事大厅综合服务窗口办理。")
    if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        notes.append(f"⚠️ 本工单为{RISK_LABELS[risk_level]}工单，请工作人员重点关注，必要时联系主管确认。")
    if risk_level == RiskLevel.CRITICAL:
        notes.append("🔴 极高风险工单：建议优先安排专人对接，核实材料真实性和代办关系合法性。")
    return notes


def _compute_deadline(appointment_date: Optional[str], risk_level: RiskLevel) -> datetime:
    now = datetime.now()
    if appointment_date:
        try:
            apt = datetime.strptime(appointment_date, "%Y-%m-%d")
            apt_deadline = apt - timedelta(hours=4)
            default_deadline = now + timedelta(days=_default_deadline_days(risk_level))
            return min(apt_deadline, default_deadline)
        except ValueError:
            pass
    return now + timedelta(days=_default_deadline_days(risk_level))


def _default_deadline_days(risk_level: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 7,
        RiskLevel.MEDIUM: 5,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 2,
    }.get(risk_level, 5)


def _build_check_summary(
    work_order_no: str,
    elder_name: str,
    item_name: str,
    appointment_date: Optional[str],
    expected_window: Optional[ServiceWindow],
    risk_level: RiskLevel,
    verify_result: VerifyResult,
    deadline: datetime,
    contact_phone: str,
    required_materials: List[MaterialSpec],
    submitted: List[SubmittedMaterial]
) -> Dict[str, Any]:
    items: List[MaterialCheckSummaryItem] = []

    submitted_by_cat: Dict = {}
    for sm in submitted:
        if sm.category not in submitted_by_cat:
            submitted_by_cat[sm.category] = []
        submitted_by_cat[sm.category].append(sm)

    missing_names = {(m.category, m.name) for m in verify_result.missing_list}
    total_required = 0
    total_ready = 0

    for req in required_materials:
        if not req.required:
            continue
        total_required += 1
        cat_submitted = submitted_by_cat.get(req.category, [])
        matched = None
        for sm in cat_submitted:
            if sm.name == req.name:
                matched = sm
                break
        is_missing = (req.category, req.name) in missing_names
        if matched and not is_missing:
            status = "✅ 已准备"
            total_ready += 1
            note = "材料合格"
        elif matched and is_missing:
            status = "⚠️ 待完善"
            note = "原件/复印件/规格有问题"
        else:
            status = "❌ 缺少"
            note = "未提交该材料"

        items.append(MaterialCheckSummaryItem(
            category=MATERIAL_LABELS.get(req.category, req.category.value),
            name=req.name,
            required=req.required,
            status=status,
            note=note,
            has_original=matched.has_original if matched else False,
            copy_count=matched.copy_count if matched else 0,
            required_copy_count=req.need_copy
        ))

    summary = PrintableCheckSummary(
        work_order_no=work_order_no,
        elder_name=elder_name,
        item_name=item_name,
        appointment_date=appointment_date,
        expected_window=WINDOW_LABELS.get(expected_window, expected_window.value if expected_window else None),
        risk_level=RISK_LABELS.get(risk_level, risk_level.value),
        total_required=total_required,
        total_ready=total_ready,
        total_missing=verify_result.total_missing,
        materials=items,
        deadline=deadline.strftime("%Y-%m-%d %H:%M"),
        contact_phone=contact_phone,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    return json.loads(summary.model_dump_json())


def _collect_ready_materials(
    required_materials: List[MaterialSpec],
    submitted: List[SubmittedMaterial],
    missing_list: List[MissingDetail]
) -> List[Dict[str, Any]]:
    missing_set = set()
    for m in missing_list:
        missing_set.add((m.category, m.name))

    submitted_by_cat: Dict = {}
    for sm in submitted:
        if sm.category not in submitted_by_cat:
            submitted_by_cat[sm.category] = []
        submitted_by_cat[sm.category].append(sm)

    ready = []
    for req in required_materials:
        if not req.required:
            continue
        key = (req.category, req.name)
        if key in missing_set:
            continue
        cat_submitted = submitted_by_cat.get(req.category, [])
        matched = None
        for sm in cat_submitted:
            if sm.name == req.name:
                matched = sm
                break
        if matched:
            ready.append({
                "category": req.category.value if hasattr(req.category, 'value') else str(req.category),
                "name": req.name,
                "has_original": matched.has_original,
                "copy_count": matched.copy_count,
                "required_copy_count": req.need_copy,
                "photo_spec": matched.photo_spec.value if matched.photo_spec else None,
                "required_photo_spec": req.need_photo_spec.value if req.need_photo_spec else None,
                "note": req.description
            })
    return ready


def _calc_supplement_progress(order, linked_orders: List[Dict]) -> Dict[str, Any]:
    total_missing = order.total_missing
    supplement_records_count = order.supplement_count
    history_missing = [o.get("total_missing", 0) for o in linked_orders]

    if order.is_pass:
        progress = 100
    elif total_missing == 0:
        progress = 100
    else:
        base_progress = int((order.total_ready / max(order.total_required, 1)) * 100)
        if supplement_records_count > 0:
            base_progress = min(99, base_progress + supplement_records_count * 5)
        progress = base_progress

    return {
        "total_missing": total_missing,
        "total_required": order.total_required,
        "total_ready": order.total_ready,
        "supplement_count": supplement_records_count,
        "completion_percent": progress,
        "history_total_missing_trend": history_missing,
        "previous_attempts": [
            {"work_order_no": o.get("work_order_no"), "total_missing": o.get("total_missing"), "created_at": o.get("created_at")}
            for o in linked_orders
        ]
    }


def _analyze_repeated_missing(order, linked_orders: List[Dict]) -> List[Dict[str, Any]]:
    if not linked_orders:
        return []

    current_missing = json.loads(order.missing_list_json) if order.missing_list_json else []
    current_missing_keys = set()
    for m in current_missing:
        key = (m.get("category"), m.get("name"))
        current_missing_keys.add(key)

    repeated = []
    for linked in linked_orders:
        try:
            linked_missing_str = None
            if isinstance(linked, dict):
                linked_missing_str = linked.get("missing_list_json", "[]")
            if linked_missing_str:
                try:
                    linked_missing = json.loads(linked_missing_str) if isinstance(linked_missing_str, str) else linked_missing_str
                except Exception:
                    linked_missing = []
            else:
                linked_missing = []
        except Exception:
            linked_missing = []

        for lm in linked_missing:
            key = (lm.get("category"), lm.get("name"))
            if key in current_missing_keys:
                repeated.append({
                    "category": lm.get("category"),
                    "name": lm.get("name"),
                    "previous_work_order_no": linked.get("work_order_no"),
                    "previous_created_at": linked.get("created_at"),
                    "missing_type": lm.get("missing_type"),
                    "reason_hint": _reason_hint(lm.get("missing_type", ""))
                })

    seen = set()
    unique = []
    for r in repeated:
        k = (r["category"], r["name"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return unique


def _reason_hint(missing_type: str) -> str:
    hints = {
        "material_missing": "上次未提交该材料，本次仍未准备",
        "original_missing": "上次缺少原件，本次仍未带原件",
        "copy_missing": "上次缺少复印件，本次仍未准备复印件",
        "copy_insufficient": "上次复印件数量不足，本次仍不足",
        "photo_spec_missing": "上次缺少符合规格的照片，本次仍未准备",
        "photo_spec_mismatch": "上次照片规格不符，本次仍未按要求拍摄",
    }
    return hints.get(missing_type, "重复缺件，需重点关注")


class PreReviewService:
    def __init__(self, db: Database, engine: RuleEngine):
        self.db = db
        self.engine = engine

    def submit_pre_review(self, req: PreReviewSubmitRequest) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        item = self.db.get_item(req.item_code)
        if not item:
            raise ValueError(f"事项编码 {req.item_code} 不存在")
        if not item.enabled:
            raise ValueError(f"事项 {item.item_name} 已暂停办理")

        expected_window = req.expected_window
        if not expected_window and req.item_code in DEFAULT_WINDOW_MAP:
            expected_window = DEFAULT_WINDOW_MAP[req.item_code]

        verify_result: VerifyResult = self.engine.validate_materials(
            item_code=req.item_code,
            elder_type=req.elder_type,
            is_agent=req.is_agent,
            agent_relation=req.agent_relation,
            submitted=req.submitted_materials
        )

        required_materials, _, _ = self.engine.get_required_materials(
            item_code=req.item_code,
            elder_type=req.elder_type,
            is_agent=req.is_agent,
            agent_relation=req.agent_relation
        )

        risk_level = _assess_risk(
            verify_result=verify_result,
            is_agent=req.is_agent,
            agent_relation=req.agent_relation,
            elder_type=req.elder_type,
            expected_window=expected_window
        )

        deadline = _compute_deadline(req.appointment_date, risk_level)

        one_time_notice = _generate_one_time_notice(
            item_name=item.item_name,
            elder_name=req.elder_name,
            risk_level=risk_level,
            verify_result=verify_result,
            deadline=deadline,
            expected_window=expected_window
        )

        window_notes = _generate_window_notes(expected_window, item.item_name, risk_level)

        missing_list = [m.model_dump(mode="json") for m in verify_result.missing_list]
        ready_materials = _collect_ready_materials(required_materials, req.submitted_materials, verify_result.missing_list)

        duplicates = self.db.find_duplicate_orders(
            item_code=req.item_code,
            elder_id_card=req.elder_id_card,
            contact_phone=req.contact_phone,
            days=7
        )
        is_duplicate = len(duplicates) > 0
        linked_original_id = duplicates[0].id if is_duplicate else None

        status = PreReviewStatus.PASSED.value if verify_result.is_pass else (
            PreReviewStatus.PENDING.value if not is_duplicate else PreReviewStatus.SUPPLEMENTING.value
        )

        total_ready = len(ready_materials)

        dummy_no = "TMP_" + datetime.now().strftime("%Y%m%d%H%M%S")
        check_summary = _build_check_summary(
            work_order_no=dummy_no,
            elder_name=req.elder_name,
            item_name=item.item_name,
            appointment_date=req.appointment_date,
            expected_window=expected_window,
            risk_level=risk_level,
            verify_result=verify_result,
            deadline=deadline,
            contact_phone=req.contact_phone,
            required_materials=required_materials,
            submitted=req.submitted_materials
        )

        order = self.db.create_pre_review_order(
            item_code=req.item_code,
            item_name=item.item_name,
            elder_type=req.elder_type.value,
            elder_id_card=req.elder_id_card,
            elder_name=req.elder_name,
            is_agent=req.is_agent,
            agent_relation=req.agent_relation.value if req.agent_relation else None,
            agent_name=req.agent_name,
            contact_phone=req.contact_phone,
            expected_window=expected_window.value if expected_window else None,
            appointment_date=req.appointment_date,
            remarks=req.remarks,
            status=status,
            risk_level=risk_level.value,
            is_pass=verify_result.is_pass,
            total_required=verify_result.total_required,
            total_missing=verify_result.total_missing,
            total_ready=total_ready,
            one_time_notice=one_time_notice,
            suggestion_deadline=deadline,
            window_notes=window_notes,
            missing_list=missing_list,
            ready_materials=ready_materials,
            check_summary=check_summary,
            is_duplicate=is_duplicate,
            linked_original_id=linked_original_id
        )

        check_summary["work_order_no"] = order.work_order_no
        self.db.update_pre_review_order(order.id, {"check_summary": check_summary})

        self.db.create_notice_record(
            work_order_id=order.id,
            work_order_no=order.work_order_no,
            notice_type="one_time_notice",
            notice_content=one_time_notice,
            notice_method="system",
            notified_to=req.agent_name or req.elder_name,
            notified_phone=req.contact_phone
        )

        order = self.db.get_pre_review_order(order.id)

        extra = {
            "missing_list": missing_list,
            "ready_materials": ready_materials,
            "check_summary": check_summary,
            "linked_original": {
                "id": duplicates[0].id,
                "work_order_no": duplicates[0].work_order_no,
                "created_at": duplicates[0].created_at.isoformat()
            } if is_duplicate else None,
            "supplement_progress": {
                "total_missing": order.total_missing,
                "total_required": order.total_required,
                "total_ready": total_ready,
                "completion_percent": int((total_ready / max(order.total_required, 1)) * 100)
            }
        }
        return order, extra

    def get_order_detail(self, order_id: int) -> Optional[Dict[str, Any]]:
        order = self.db.get_pre_review_order(order_id)
        if not order:
            return None

        missing_list = json.loads(order.missing_list_json) if order.missing_list_json else []
        ready_materials = json.loads(order.ready_materials_json) if order.ready_materials_json else []
        check_summary = json.loads(order.check_summary_json) if order.check_summary_json else {}

        linked_orders = self.db.get_linked_orders(
            elder_id_card=order.elder_id_card,
            contact_phone=order.contact_phone,
            item_code=order.item_code,
            exclude_id=order.id
        )

        supplement_progress = _calc_supplement_progress(order, linked_orders)
        repeated_missing = _analyze_repeated_missing(order, linked_orders)
        notice_records = [n.model_dump(mode="json") for n in self.db.list_notice_records(work_order_id=order.id)]

        return {
            "order": order.model_dump(mode="json"),
            "missing_list": missing_list,
            "ready_materials": ready_materials,
            "check_summary": check_summary,
            "linked_orders": linked_orders,
            "supplement_progress": supplement_progress,
            "repeated_missing_reasons": repeated_missing,
            "notice_records": notice_records
        }

    def supplement_review(self, req: Dict[str, Any]) -> Dict[str, Any]:
        work_order_id = req["work_order_id"]
        order = self.db.get_pre_review_order(work_order_id)
        if not order:
            raise ValueError(f"工单ID {work_order_id} 不存在")

        supplemented = req.get("supplemented_materials", [])
        review_result = req.get("review_result", False)
        reviewer = req.get("reviewer", "")
        review_remark = req.get("review_remark", "")

        item = self.db.get_item(order.item_code)
        missing_before = order.total_missing

        original_ready_materials = json.loads(order.ready_materials_json) if order.ready_materials_json else []

        if supplemented and item:
            from .schemas import SubmittedMaterial as SM
            submats = [SM(**m) if isinstance(m, dict) else m for m in supplemented]

            merged_submitted = []
            seen_keys = set()
            for rm in original_ready_materials:
                key = (rm.get("category"), rm.get("name"))
                if key not in seen_keys:
                    seen_keys.add(key)
                    try:
                        merged_submitted.append(SM(**rm))
                    except Exception:
                        pass
            for sm in submats:
                key = (sm.category, sm.name)
                if key not in seen_keys:
                    seen_keys.add(key)
                    merged_submitted.append(sm)

            try:
                verify_result = self.engine.validate_materials(
                    item_code=order.item_code,
                    elder_type=ElderType(order.elder_type),
                    is_agent=order.is_agent,
                    agent_relation=AgentRelation(order.agent_relation) if order.agent_relation else None,
                    submitted=merged_submitted
                )
                missing_after = verify_result.total_missing
                is_pass_new = verify_result.is_pass
                missing_list_new = [m.model_dump(mode="json") for m in verify_result.missing_list]
                ready_materials_new = _collect_ready_materials(
                    self.engine.get_required_materials(
                        item_code=order.item_code,
                        elder_type=ElderType(order.elder_type),
                        is_agent=order.is_agent,
                        agent_relation=AgentRelation(order.agent_relation) if order.agent_relation else None
                    )[0],
                    merged_submitted,
                    verify_result.missing_list
                )
                total_ready_new = len(ready_materials_new)
            except Exception:
                missing_after = max(0, missing_before - len(supplemented))
                is_pass_new = missing_after == 0
                missing_list_new = json.loads(order.missing_list_json)
                total_ready_new = order.total_ready
                ready_materials_new = original_ready_materials
        else:
            missing_after = 0 if review_result else max(0, missing_before - 1)
            is_pass_new = review_result
            missing_list_new = [] if review_result else json.loads(order.missing_list_json)
            total_ready_new = order.total_required if review_result else order.total_ready
            ready_materials_new = original_ready_materials

        updates = {
            "total_missing": missing_after,
            "total_ready": total_ready_new,
            "is_pass": is_pass_new,
            "missing_list": missing_list_new,
            "ready_materials": ready_materials_new,
        }

        if is_pass_new:
            updates["status"] = PreReviewStatus.PASSED.value
        else:
            updates["status"] = PreReviewStatus.SUPPLEMENTING.value

        self.db.update_pre_review_order(order.id, updates)

        supp_data = self.db.create_supplement_review(
            work_order_id=order.id,
            work_order_no=order.work_order_no,
            reviewer=reviewer,
            review_result=is_pass_new,
            missing_before=missing_before,
            missing_after=missing_after,
            review_remark=review_remark,
            supplemented_materials=[m.model_dump(mode="json") if hasattr(m, 'model_dump') else (m if isinstance(m, dict) else {}) for m in supplemented]
        )

        self.db.create_notice_record(
            work_order_id=order.id,
            work_order_no=order.work_order_no,
            notice_type="supplement_review",
            notice_content=(f"复核结果：{'通过' if is_pass_new else '仍需补齐'}。缺件从{missing_before}项降至{missing_after}项。{review_remark or ''}").strip(),
            notice_method="manual",
            notified_to=order.agent_name or order.elder_name,
            notified_phone=order.contact_phone
        )

        updated = self.db.get_pre_review_order(order.id)
        return {
            "order": updated.model_dump(mode="json"),
            "supplement_record": supp_data,
            "missing_before": missing_before,
            "missing_after": missing_after,
            "review_passed": is_pass_new
        }
