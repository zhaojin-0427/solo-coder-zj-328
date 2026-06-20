from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from ..db_utils import now_iso, enum_value, json_dumps, bool_to_int, generate_no
from ..schemas import ResponsibleRole


EXCEPTION_TYPE_NAMES = {
    "window_reject": "窗口退回",
    "material_invalid": "材料被判无效",
    "elder_absent": "老人未到场",
    "companion_late": "陪同人迟到",
    "supplement_fail": "现场补件失败",
    "policy_changed": "窗口政策变更",
    "elder_unwell": "老人身体不适",
    "other": "其他异常"
}


def _generate_exception_no(dt: datetime) -> str:
    return generate_no("EX", dt)


def _generate_disposal_plan(
    exception_type: str,
    elder_type: Optional[str],
    risk_level: Optional[str],
    impact_completion: bool,
    item_code: Optional[str]
) -> Dict[str, Any]:
    now = datetime.now()

    urgent_types = ["elder_unwell", "elder_absent"]
    high_types = ["window_reject", "material_invalid", "policy_changed", "companion_late"]
    medium_types = ["supplement_fail"]

    if exception_type in urgent_types:
        base_priority = "p1_urgent"
    elif exception_type in high_types:
        base_priority = "p2_high"
    elif exception_type in medium_types:
        base_priority = "p3_medium"
    else:
        base_priority = "p4_low"

    priority_levels = {
        "p1_urgent": 4,
        "p2_high": 3,
        "p3_medium": 2,
        "p4_low": 1
    }
    current_level = priority_levels[base_priority]

    if risk_level == "critical":
        current_level = min(current_level + 2, 4)
    elif risk_level == "high":
        current_level = min(current_level + 1, 4)

    if elder_type in ("special_elder", "disabled", "low_income"):
        current_level = min(current_level + 1, 4)

    if impact_completion:
        current_level = min(current_level + 1, 4)

    level_to_priority = {v: k for k, v in priority_levels.items()}
    priority = level_to_priority[current_level]

    deadline_hours = {
        "p1_urgent": 1,
        "p2_high": 4,
        "p3_medium": 24,
        "p4_low": 72
    }
    latest_deadline = now + timedelta(hours=deadline_hours.get(priority, 24))
    follow_up_deadline = now + timedelta(days=3)

    type_role_map = {
        "window_reject": ResponsibleRole.WINDOW_STAFF.value,
        "material_invalid": ResponsibleRole.WINDOW_STAFF.value,
        "elder_absent": ResponsibleRole.COMMUNITY_WORKER.value,
        "companion_late": ResponsibleRole.ACCOMPANY_MANAGER.value,
        "supplement_fail": ResponsibleRole.WINDOW_STAFF.value,
        "policy_changed": ResponsibleRole.SUPERVISOR.value,
        "elder_unwell": ResponsibleRole.MEDICAL_STAFF.value,
        "other": ResponsibleRole.SUPERVISOR.value
    }
    responsible_role = type_role_map.get(exception_type, ResponsibleRole.SUPERVISOR.value)

    type_actions_map = {
        "window_reject": [
            "立即核实退回原因，与窗口确认最新政策要求",
            "联系老人或家属说明情况，解释退回复核要点",
            "协助重新准备缺失或不符合要求的材料",
            "安排二次预审或预约下次办理时间"
        ],
        "material_invalid": [
            "确认材料无效的具体原因（过期、复印不清、信息不符等）",
            "告知家属需要重新准备的材料清单和规范",
            "协调社区或相关部门出具证明材料",
            "跟踪材料重新准备进度"
        ],
        "elder_absent": [
            "联系家属确认老人未到场原因",
            "如为身体原因，协调上门服务或改期办理",
            "评估是否需要安排陪同服务",
            "记录老人情况并持续关注"
        ],
        "companion_late": [
            "联系陪同人确认位置和预计到达时间",
            "如陪同人无法按时到达，协调备用陪同人",
            "与窗口沟通延迟取号或改期",
            "事后评估陪同资源调度机制"
        ],
        "supplement_fail": [
            "分析补件失败的具体环节和原因",
            "与材料出具部门协调加急处理",
            "安排专人协助办理补充材料",
            "视情况启动容缺受理或绿色通道"
        ],
        "policy_changed": [
            "获取窗口最新政策文件和执行标准",
            "更新系统事项配置和材料清单",
            "通知近期预约老人政策变动情况",
            "开展窗口人员培训确保政策统一执行"
        ],
        "elder_unwell": [
            "立即联系医护人员或拨打急救电话",
            "安抚老人情绪并提供临时休息场所",
            "通知家属老人情况",
            "评估老人身体状况，改期或安排上门办理"
        ],
        "other": [
            "调查核实异常具体情况",
            "协调相关责任部门处理",
            "保持与老人和家属的沟通",
            "记录异常原因形成案例库"
        ]
    }
    suggested_actions = type_actions_map.get(exception_type, type_actions_map["other"])

    if impact_completion:
        suggested_actions.append("【重要】该异常已影响事项办理进度，需优先处理并跟踪至完成")

    if risk_level in ("high", "critical"):
        suggested_actions.append("【风险提示】涉及高风险老人，处置过程需特别关注老人安全与感受")

    follow_up_required = True
    if exception_type in ("other",) and not impact_completion and risk_level in ("low", "medium"):
        follow_up_required = False

    return {
        "priority": priority,
        "responsible_role": responsible_role,
        "suggested_actions": suggested_actions,
        "latest_deadline": latest_deadline,
        "follow_up_required": follow_up_required,
        "follow_up_deadline": follow_up_deadline if follow_up_required else None
    }


def fetch_source_info(source_type: str, source_id: int, repo) -> Optional[Dict[str, Any]]:
    return repo.fetch_source_info(source_type, source_id)


def create_exception(data: Dict[str, Any], repo) -> Any:
    source_type = enum_value(data["source_type"])
    source_id = data["source_id"]

    if not repo.check_source_exists(source_type, source_id):
        type_names = {
            "verify_record": "材料校验记录",
            "pre_review_order": "预审工单",
            "accompany_appointment": "陪同预约单"
        }
        type_name = type_names.get(source_type, source_type)
        raise ValueError(f"关联的{type_name}(ID={source_id})不存在")

    item_code = None
    item_name = None
    elder_name = None
    elder_type = None
    community = None
    expected_window = None

    source_info = repo.fetch_source_info(source_type, source_id)
    if source_info:
        if source_type == "verify_record":
            record = source_info.get("record")
            if record:
                if hasattr(record, "item_code"):
                    item_code = record.item_code
                    item_name = record.item_name
                    elder_type = record.elder_type
                else:
                    item_code = record.get("item_code")
                    item_name = record.get("item_name")
                    elder_type = record.get("elder_type")
        elif source_type == "pre_review_order":
            item_code = source_info.get("item_code")
            item_name = source_info.get("item_name")
            elder_name = source_info.get("elder_name")
            elder_type = source_info.get("elder_type")
            expected_window = source_info.get("expected_window")
        elif source_type == "accompany_appointment":
            item_code = source_info.get("item_code")
            item_name = source_info.get("item_name")
            elder_name = source_info.get("elder_name")
            elder_type = source_info.get("elder_type")
            community = source_info.get("community")
            expected_window = source_info.get("expected_window")

    if elder_type in ("special_elder", "disabled", "low_income"):
        derived_risk = "high"
    elif elder_type == "remote_resident":
        derived_risk = "medium"
    else:
        derived_risk = "medium"

    exception_type_val = enum_value(data["exception_type"])

    disposal_plan = _generate_disposal_plan(
        exception_type=exception_type_val,
        elder_type=elder_type,
        risk_level=derived_risk,
        impact_completion=data.get("impact_completion", True),
        item_code=item_code
    )

    now = datetime.now()
    exception_no = _generate_exception_no(now)

    repo.insert_exception(
        exception_no=exception_no,
        exception_type=exception_type_val,
        source_type=source_type,
        source_id=source_id,
        item_code=item_code,
        item_name=item_name,
        elder_name=elder_name,
        elder_type=elder_type,
        community=community,
        expected_window=expected_window,
        reporter=data["reporter"],
        reporter_role=data["reporter_role"],
        reporter_phone=data.get("reporter_phone"),
        description=data["description"],
        location=data.get("location"),
        impact_completion=data.get("impact_completion", True),
        risk_level=derived_risk,
        priority=disposal_plan["priority"],
        responsible_role=disposal_plan["responsible_role"],
        suggested_actions=disposal_plan["suggested_actions"],
        latest_deadline=disposal_plan["latest_deadline"],
        follow_up_required=disposal_plan["follow_up_required"],
        follow_up_deadline=disposal_plan["follow_up_deadline"],
        evidence_images=data.get("evidence_images", []),
        extra_info=data.get("extra_info", {}),
        now=now
    )

    repo.insert_exception_status_history(
        exception_id=None,
        from_status=None,
        to_status="pending",
        operator="system",
        remark=f"异常事件自动创建并生成处置单，优先级：{disposal_plan['priority']}",
        now=now,
        exception_no=exception_no
    )

    return repo.get_exception_by_no(exception_no)
