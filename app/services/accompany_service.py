from typing import List, Dict, Any, Optional
from datetime import datetime

from ..db_utils import now_iso, enum_value, json_dumps, bool_to_int, int_to_bool, generate_no, json_loads
from ..schemas import MatchedCompanion


def _calculate_risk_level(elder_type: str, mobility_level: str, is_living_alone: bool, missing_count: int) -> str:
    score = 0
    if elder_type in ("special_elder", "disabled", "low_income"):
        score += 2
    if mobility_level == "bedridden":
        score += 3
    elif mobility_level == "wheelchair":
        score += 2
    elif mobility_level == "need_assist":
        score += 1
    if is_living_alone:
        score += 2
    if missing_count >= 3:
        score += 2
    elif missing_count >= 1:
        score += 1
    if score >= 6:
        return "critical"
    elif score >= 4:
        return "high"
    elif score >= 2:
        return "medium"
    else:
        return "low"


def _calculate_match_priority(risk_level: str, is_living_alone: bool) -> int:
    if risk_level == "critical":
        return 1
    elif risk_level == "high" or is_living_alone:
        return 2
    else:
        return 3


def _match_companions(repo, community: str, item_code: str, expected_window: Optional[str], risk_level: str, expected_date: str, limit: int = 5) -> List[MatchedCompanion]:
    candidates = repo.query_companion_candidates(
        community=community,
        item_code=item_code,
        expected_window=expected_window,
        risk_level=risk_level,
        expected_date=expected_date
    )
    scored = []
    for cand in candidates:
        score = 0.0
        reasons = []
        cr_type = cand["companion_type"]
        if risk_level in ("high", "critical") and cr_type == "social_worker":
            score += 30
            reasons.append("社工资质适合高风险老人")
        elif cr_type == "volunteer":
            score += 15
            reasons.append("社区志愿者")
        elif cr_type == "family":
            score += 20
            reasons.append("家属陪同")
        eligible = cand.get("eligible_items", [])
        if item_code in eligible:
            score += 25
            reasons.append(f"具备{item_code}事项陪同经验")
        windows = cand.get("available_windows", [])
        if expected_window and expected_window in windows:
            score += 20
            reasons.append(f"可服务于{expected_window}窗口")
        elif not windows:
            score += 10
            reasons.append("无窗口限制")
        daily_count = cand.get("daily_count", 0)
        max_daily = cand.get("max_daily_count", 3)
        if daily_count < max_daily:
            score += 15
            reasons.append(f"当日尚有{max_daily - daily_count}个服务名额")
        else:
            score -= 20
            reasons.append("当日服务名额已满")
        scored.append({
            "candidate": cand,
            "score": score,
            "reasons": reasons
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    results = []
    for idx, s in enumerate(scored[:limit]):
        c = s["candidate"]
        results.append(MatchedCompanion(
            companion_id=c["id"],
            companion_name=c["name"],
            companion_type=c["companion_type"],
            phone=c["phone"],
            community=c["community"],
            match_priority=idx + 1,
            match_score=round(s["score"], 2),
            match_reasons=s["reasons"]
        ))
    return results


def _generate_material_reminders(repo, missing_materials: List[Dict[str, Any]], item_code: str) -> List[str]:
    reminders = []
    item = repo.get_item(item_code)
    if item:
        all_mats = item.base_materials + item.agent_required_materials
        for m in all_mats:
            if m.required:
                reminders.append(f"请务必携带：{m.name}" + (f"（需原件{m.need_original and '、复印件×' + str(m.need_copy) if m.need_copy > 0 else ''}）" if m.need_original or m.need_copy > 0 else ""))
    for mm in missing_materials:
        reminders.append(f"注意：上次预审缺件【{mm.get('name', '未知材料')}】，请务必补齐")
    if not reminders:
        reminders.append("请携带身份证等基础证件前往")
    return reminders


def _generate_route_hints(community: str, expected_window: Optional[str]) -> List[str]:
    hints = [
        f"从{community}出发，建议提前30分钟到达服务中心",
        "请携带老年卡或身份证以便取号排队"
    ]
    if expected_window:
        window_names = {
            "medical_window": "医保窗口",
            "social_security_window": "社保窗口",
            "banking_window": "银行窗口",
            "civil_affairs_window": "民政窗口",
            "comprehensive_window": "综合窗口",
            "registration_window": "登记窗口"
        }
        hints.append(f"办理窗口：{window_names.get(expected_window, expected_window)}，位于服务大厅一层")
    hints.append("服务中心配备无障碍通道和轮椅租借服务")
    return hints


def _generate_risk_alerts(risk_level: str, mobility_level: str, is_living_alone: bool, missing_count: int) -> List[str]:
    alerts = []
    if risk_level == "critical":
        alerts.append("【紧急】该老人为极高风险人群，需安排专业社工陪同")
    elif risk_level == "high":
        alerts.append("【重要】该老人为高风险人群，建议优先派单")
    if mobility_level == "bedridden":
        alerts.append("老人卧床，需安排上门接送服务")
    elif mobility_level == "wheelchair":
        alerts.append("老人使用轮椅，需安排无障碍路线和志愿者协助")
    elif mobility_level == "need_assist":
        alerts.append("老人行动不便，需有人搀扶协助")
    if is_living_alone:
        alerts.append("老人独居，需特别关注其安全状态")
    if missing_count > 0:
        alerts.append(f"存在{missing_count}项缺件，需提醒老人或家属提前补齐材料")
    return alerts


def create_accompany_appointment(data: Dict[str, Any], repo) -> Dict[str, Any]:
    item = repo.get_item(data["item_code"])
    if not item:
        raise ValueError(f"事项编码 {data['item_code']} 不存在")
    item_name = item.item_name
    missing_materials = []
    missing_count = 0
    if data.get("pre_review_order_id"):
        pr_order = repo.get_pre_review_order(data["pre_review_order_id"])
        if pr_order:
            missing_list = json_loads(pr_order.missing_list_json)
            missing_materials = missing_list
            missing_count = pr_order.total_missing
    elif data.get("verify_history_id"):
        hd = repo.get_history_detail(data["verify_history_id"])
        if hd:
            missing_materials = hd.get("missing_details", [])
            missing_count = len(missing_materials)
    risk_level = _calculate_risk_level(
        enum_value(data["elder_type"]),
        enum_value(data["mobility_level"]),
        data.get("is_living_alone", False),
        missing_count
    )
    match_priority = _calculate_match_priority(risk_level, data.get("is_living_alone", False))
    expected_window_val = enum_value(data.get("expected_window"))
    matched = _match_companions(
        repo=repo,
        community=data["community"],
        item_code=data["item_code"],
        expected_window=expected_window_val,
        risk_level=risk_level,
        expected_date=data["expected_date"]
    )
    primary = matched[0] if matched else None
    material_reminders = _generate_material_reminders(repo, missing_materials, data["item_code"])
    route_hints = _generate_route_hints(data["community"], expected_window_val)
    risk_alerts = _generate_risk_alerts(
        risk_level,
        enum_value(data["mobility_level"]),
        data.get("is_living_alone", False),
        missing_count
    )
    now = datetime.now()
    appointment_no = generate_no("AC", now)
    status = "matched" if primary else "pending_match"
    expected_service_period = "上午 09:00-11:30"

    repo.insert_accompany_appointment(
        appointment_no=appointment_no,
        data=data,
        item_name=item_name,
        expected_window_val=expected_window_val,
        status=status,
        risk_level=risk_level,
        match_priority=match_priority,
        missing_materials=missing_materials,
        primary=primary,
        expected_service_period=expected_service_period,
        material_reminders=material_reminders,
        route_hints=route_hints,
        risk_alerts=risk_alerts,
        now=now
    )

    new_id = repo.get_appointment_id_by_no(appointment_no)
    for m in matched:
        repo.insert_match_candidate(
            appointment_id=new_id,
            companion=m,
            now=now
        )
    repo.insert_accompany_status_history(
        appointment_id=new_id,
        appointment_no=appointment_no,
        from_status=None,
        to_status=status,
        operator="system",
        remark="预约创建并自动匹配",
        now=now
    )

    appointment = repo.get_accompany_appointment(new_id)
    return {
        "appointment": appointment,
        "matched_candidates": matched
    }
