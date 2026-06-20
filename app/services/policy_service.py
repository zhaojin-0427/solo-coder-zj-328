from typing import Dict, Any, Optional, List
from datetime import datetime

from ..db_utils import now_iso, enum_value, json_dumps, json_loads


def scan_policy_impact(policy_id: int, repo) -> Dict[str, Any]:
    policy = repo.get_policy_change(policy_id)
    if not policy:
        return {"error": "政策变更不存在"}

    applicable_items = policy.applicable_items
    applicable_windows = policy.applicable_windows
    impacted_elder_types = policy.impacted_elder_types

    scan_results = {
        "verify_records": {"count": 0, "ids": []},
        "pre_review_orders": {"count": 0, "ids": []},
        "accompany_appointments": {"count": 0, "ids": []},
        "exception_orders": {"count": 0, "ids": []},
        "service_items": {"count": 0, "ids": []}
    }

    new_warnings_count = 0

    if applicable_items:
        verify_records = repo.scan_verify_records_by_items(applicable_items)
        scan_results["verify_records"]["count"] = len(verify_records)
        scan_results["verify_records"]["ids"] = [r["id"] for r in verify_records]

        for r in verify_records:
            impact_details = _build_verify_impact_details(policy, r)
            warning_risk = _determine_warning_risk(policy.risk_level, r.get("elder_type"), impacted_elder_types)
            repo.insert_policy_warning(
                policy_change_id=policy_id,
                policy_title=policy.title,
                source_type="verify_record",
                source_id=r["id"],
                source_no=None,
                item_code=r.get("item_code"),
                item_name=r.get("item_name"),
                elder_name=None,
                elder_type=r.get("elder_type"),
                community=None,
                expected_window=None,
                appointment_date=None,
                risk_level=warning_risk,
                impact_details=impact_details
            )
            new_warnings_count += 1

        pr_orders = repo.scan_pre_review_orders_by_items(applicable_items, applicable_windows, impacted_elder_types)
        scan_results["pre_review_orders"]["count"] = len(pr_orders)
        scan_results["pre_review_orders"]["ids"] = [r["id"] for r in pr_orders]

        for r in pr_orders:
            impact_details = _build_pre_review_impact_details(policy, r)
            warning_risk = _determine_warning_risk(policy.risk_level, r.get("elder_type"), impacted_elder_types)
            repo.insert_policy_warning(
                policy_change_id=policy_id,
                policy_title=policy.title,
                source_type="pre_review_order",
                source_id=r["id"],
                source_no=r.get("work_order_no"),
                item_code=r.get("item_code"),
                item_name=r.get("item_name"),
                elder_name=r.get("elder_name"),
                elder_type=r.get("elder_type"),
                community=None,
                expected_window=r.get("expected_window"),
                appointment_date=r.get("appointment_date"),
                risk_level=warning_risk,
                impact_details=impact_details
            )
            new_warnings_count += 1

        acc_appointments = repo.scan_accompany_appointments_by_items(applicable_items, applicable_windows, impacted_elder_types)
        scan_results["accompany_appointments"]["count"] = len(acc_appointments)
        scan_results["accompany_appointments"]["ids"] = [r["id"] for r in acc_appointments]

        for r in acc_appointments:
            impact_details = _build_accompany_impact_details(policy, r)
            warning_risk = _determine_warning_risk(policy.risk_level, r.get("elder_type"), impacted_elder_types)
            repo.insert_policy_warning(
                policy_change_id=policy_id,
                policy_title=policy.title,
                source_type="accompany_appointment",
                source_id=r["id"],
                source_no=r.get("appointment_no"),
                item_code=r.get("item_code"),
                item_name=r.get("item_name"),
                elder_name=r.get("elder_name"),
                elder_type=r.get("elder_type"),
                community=r.get("community"),
                expected_window=r.get("expected_window"),
                appointment_date=r.get("expected_date"),
                risk_level=warning_risk,
                impact_details=impact_details
            )
            new_warnings_count += 1

        exc_orders = repo.scan_exception_orders_by_items(applicable_items)
        scan_results["exception_orders"]["count"] = len(exc_orders)
        scan_results["exception_orders"]["ids"] = [r["id"] for r in exc_orders]

        svc_items = repo.scan_service_items_by_codes(applicable_items)
        scan_results["service_items"]["count"] = len(svc_items)
        scan_results["service_items"]["ids"] = [r["id"] for r in svc_items]

    total_affected_count = sum(v["count"] for v in scan_results.values())

    return {
        "policy_id": policy_id,
        "policy_title": policy.title,
        "new_warnings_count": new_warnings_count,
        "total_affected_count": total_affected_count,
        "scanned_sources": scan_results
    }


def query_policy_impact(elder_type: Optional[str], item_code: Optional[str], community: Optional[str], expected_window: Optional[str], appointment_date: Optional[str], repo) -> Dict[str, Any]:
    active_policies = repo.query_active_policies(
        elder_type=elder_type,
        item_code=item_code,
        expected_window=expected_window
    )

    if not active_policies:
        return {
            "is_affected": False,
            "affected_policies": [],
            "added_materials": [],
            "removed_materials": [],
            "rejection_reasons": [],
            "need_re_preview": False,
            "need_re_appointment": False,
            "suggestions": []
        }

    all_added = []
    all_removed = []
    all_reasons = []
    suggestions = []

    for p in active_policies:
        policy_data = p if isinstance(p, dict) else p.model_dump(mode="json")
        if item_code and item_code not in policy_data.get("applicable_items", []):
            continue
        if elder_type and elder_type not in policy_data.get("impacted_elder_types", []):
            continue
        if expected_window and expected_window not in policy_data.get("applicable_windows", []):
            continue

        all_added.extend(policy_data.get("added_materials", []))
        all_removed.extend(policy_data.get("removed_materials", []))
        all_reasons.extend(policy_data.get("rejection_reasons", []))

        if policy_data.get("handling_suggestion"):
            suggestions.append(policy_data["handling_suggestion"])

    need_re_preview = len(all_added) > 0 or len(all_removed) > 0
    need_re_appointment = len(all_reasons) > 0

    return {
        "is_affected": True,
        "affected_policies": [p if isinstance(p, dict) else p.model_dump(mode="json") for p in active_policies],
        "added_materials": all_added,
        "removed_materials": all_removed,
        "rejection_reasons": all_reasons,
        "need_re_preview": need_re_preview,
        "need_re_appointment": need_re_appointment,
        "suggestions": suggestions
    }


def get_policy_change_detail(policy_id: int, repo) -> Optional[Dict[str, Any]]:
    policy = repo.get_policy_change(policy_id)
    if not policy:
        return None

    warnings = repo.list_warnings_by_policy_id(policy_id)
    warning_count = len(warnings)
    confirmed_warning_count = sum(1 for w in warnings if (w.status if hasattr(w, 'status') else w.get("status")) == "confirmed")

    impact_summary = {
        "total_warnings": warning_count,
        "confirmed_warnings": confirmed_warning_count,
        "unconfirmed_warnings": warning_count - confirmed_warning_count,
        "added_materials": policy.added_materials if hasattr(policy, 'added_materials') else policy.get("added_materials", []),
        "removed_materials": policy.removed_materials if hasattr(policy, 'removed_materials') else policy.get("removed_materials", []),
        "applicable_items": policy.applicable_items if hasattr(policy, 'applicable_items') else policy.get("applicable_items", []),
        "applicable_windows": policy.applicable_windows if hasattr(policy, 'applicable_windows') else policy.get("applicable_windows", [])
    }

    return {
        "policy": policy,
        "impact_summary": impact_summary,
        "warning_count": warning_count,
        "confirmed_warning_count": confirmed_warning_count
    }


def _determine_warning_risk(policy_risk_level: str, elder_type: Optional[str], impacted_elder_types: List[str]) -> str:
    if policy_risk_level in ("high", "critical"):
        return policy_risk_level
    if elder_type in ("special_elder", "disabled", "low_income"):
        return "high"
    if elder_type in impacted_elder_types:
        return policy_risk_level
    return policy_risk_level


def _build_verify_impact_details(policy, record: Dict) -> List[Dict[str, Any]]:
    details = []
    for mat in (policy.added_materials if hasattr(policy, 'added_materials') else []):
        details.append({"type": "material_add", "material": mat, "description": f"政策要求新增材料：{mat.get('name', '') if isinstance(mat, dict) else mat}"})
    for mat in (policy.removed_materials if hasattr(policy, 'removed_materials') else []):
        details.append({"type": "material_remove", "material": mat, "description": f"政策废止材料：{mat.get('name', '') if isinstance(mat, dict) else mat}"})
    for reason in (policy.rejection_reasons if hasattr(policy, 'rejection_reasons') else []):
        details.append({"type": "rejection_risk", "description": f"退回风险：{reason}"})
    return details


def _build_pre_review_impact_details(policy, order: Dict) -> List[Dict[str, Any]]:
    details = _build_verify_impact_details(policy, order)
    if hasattr(policy, 'handling_suggestion') and policy.handling_suggestion:
        details.append({"type": "handling_suggestion", "description": policy.handling_suggestion})
    return details


def _build_accompany_impact_details(policy, appointment: Dict) -> List[Dict[str, Any]]:
    details = _build_verify_impact_details(policy, appointment)
    if hasattr(policy, 'handling_suggestion') and policy.handling_suggestion:
        details.append({"type": "handling_suggestion", "description": policy.handling_suggestion})
    return details
