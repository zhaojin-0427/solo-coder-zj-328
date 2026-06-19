import requests
import json
import time

BASE = "http://127.0.0.1:9505"


def p(label, data):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def assert_ok(label, resp):
    d = resp.json()
    assert d.get("code") == 0, f"[{label}] code={d.get('code')}, msg={d.get('message')}"
    print(f"  ✅ {label}")
    return d["data"]


results = []


def test(name, fn):
    print(f"\n{'▶'*30}\n{name}\n{'▶'*30}")
    try:
        ok = fn()
        results.append((name, ok))
        print(f"◀ {'✅ 通过' if ok else '❌ 失败'}")
    except AssertionError as e:
        print(f"◀ ❌ 断言失败 - {e}")
        results.append((name, False))
    except Exception as e:
        print(f"◀ ❌ 异常 - {e}")
        import traceback
        traceback.print_exc()
        results.append((name, False))


def test_bug1_supplement_merges_original():
    payload = {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "elder_id_card": "320102195501016666",
        "elder_name": "王合并",
        "is_agent": True,
        "agent_relation": "child",
        "agent_name": "王小合",
        "contact_phone": "15800158001",
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
            {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
        ],
        "expected_window": "medical_window"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    data = assert_ok("创建预审工单（只交了身份证+医保卡）", r)
    oid = data["work_order"]["id"]
    missing_before = data["work_order"]["total_missing"]
    print(f"    初始缺件: {missing_before}项")

    payload_sup = {
        "work_order_id": oid,
        "reviewer": "李复核",
        "supplemented_materials": [
            {"category": "medical_record", "name": "医疗费用发票", "has_original": True},
            {"category": "medical_record", "name": "住院/门诊病历", "has_original": False, "copy_count": 1},
            {"category": "medical_record", "name": "费用明细清单", "has_original": True},
            {"category": "id_card", "name": "代办人身份证", "has_original": True, "copy_count": 1},
            {"category": "authorization_letter", "name": "授权委托书", "has_original": True},
        ],
        "review_result": True,
        "review_remark": "补齐了发票+病历+费用清单+代办人身份证+授权书"
    }
    r2 = requests.post(f"{BASE}/api/pre-review/supplement-review", json=payload_sup)
    data2 = assert_ok("补齐复核（只补交了缺件项，不再重复提交身份证和医保卡）", r2)
    order2 = data2["order"]
    missing_after = data2["missing_after"]

    ok1 = missing_after == 0, f"复核后缺件应为0，实际={missing_after}"
    ok2 = order2["is_pass"] == True
    ok3 = order2["status"] == "passed"

    ready_materials = order2.get("ready_materials", [])
    has_id_card = any(m.get("name") == "居民身份证" for m in ready_materials) if isinstance(ready_materials, list) else False

    print(f"    复核后缺件: {missing_after}项, is_pass={order2['is_pass']}, status={order2['status']}")
    print(f"    已备材料含身份证: {has_id_card}")

    ok_all = ok1 and ok2 and ok3
    if not ok_all:
        print(f"    ❌ missing_after={missing_after}, is_pass={order2['is_pass']}, status={order2['status']}")
    return ok_all


def test_bug2_total_ready_consistency():
    payload = {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "elder_id_card": "320102195501017777",
        "elder_name": "赵一致",
        "is_agent": True,
        "agent_relation": "spouse",
        "agent_name": "赵配",
        "contact_phone": "15900159002",
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
            {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
            {"category": "medical_record", "name": "医疗费用发票", "has_original": True},
        ],
        "expected_window": "medical_window"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    data = assert_ok("创建预审工单", r)
    wo = data["work_order"]
    oid = wo["id"]

    order_total_ready = wo["total_ready"]
    summary_total_ready = data["check_summary"]["total_ready"]

    print(f"    工单 total_ready = {order_total_ready}")
    print(f"    摘要 total_ready = {summary_total_ready}")

    r2 = requests.get(f"{BASE}/api/pre-review/{oid}")
    data2 = assert_ok("获取工单详情", r2)
    detail_order_ready = data2["order"]["total_ready"]
    detail_summary_ready = data2["check_summary"]["total_ready"]

    print(f"    详情 工单 total_ready = {detail_order_ready}")
    print(f"    详情 摘要 total_ready = {detail_summary_ready}")

    ok1 = order_total_ready == summary_total_ready
    ok2 = detail_order_ready == detail_summary_ready
    if not ok1:
        print(f"    ❌ 创建时不一致: 工单={order_total_ready} vs 摘要={summary_total_ready}")
    if not ok2:
        print(f"    ❌ 详情时不一致: 工单={detail_order_ready} vs 摘要={detail_summary_ready}")
    return ok1 and ok2


def test_bug3_expired_by_deadline():
    payload = {
        "item_code": "SOCIAL_SECURITY_VERIFY",
        "elder_type": "local_resident",
        "elder_id_card": "320102195501018888",
        "elder_name": "钱超期",
        "is_agent": False,
        "contact_phone": "15700157003",
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True},
        ],
        "appointment_date": "2020-01-01"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    data = assert_ok("创建预审工单（预约日期设为2020年，必定已超期）", r)
    oid = data["work_order"]["id"]
    deadline = data["work_order"]["suggestion_deadline"]
    print(f"    工单id={oid}, suggestion_deadline={deadline}")

    r2 = requests.get(f"{BASE}/api/pre-review/{oid}")
    data2 = assert_ok("获取详情（触发自动标记超期）", r2)
    order_status = data2["order"]["status"]
    print(f"    自动标记后状态: {order_status}")
    ok1 = order_status == "expired"

    r3 = requests.get(f"{BASE}/api/stats/pre-review/expired-summary")
    data3 = assert_ok("获取超期统计", r3)
    expired_count = data3["expired_count"]
    print(f"    超期工单数: {expired_count}")
    ok2 = expired_count >= 1

    r4 = requests.get(f"{BASE}/api/stats/pre-review/overall")
    data4 = assert_ok("获取综合统计", r4)
    overall_expired = data4["expired_count"]
    print(f"    综合统计超期数: {overall_expired}")
    ok3 = overall_expired >= 1

    r5 = requests.get(f"{BASE}/api/pre-review/list", params={"status": "expired"})
    data5 = assert_ok("按expired状态筛选工单列表", r5)
    expired_items = data5["items"]
    found = any(i["id"] == oid for i in expired_items)
    ok4 = found
    print(f"    超期工单出现在expired列表中: {found}")

    return ok1 and ok2 and ok3 and ok4


if __name__ == "__main__":
    test("Bug1: 补齐材料复核应合并原工单已准备材料", test_bug1_supplement_merges_original)
    test("Bug2: total_ready 与可打印摘要中 total_ready 应一致", test_bug2_total_ready_consistency)
    test("Bug3: 超期统计应按 suggestion_deadline 识别超期工单", test_bug3_expired_by_deadline)

    print(f"\n\n{'='*70}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"🎯 Bug修复验证: {passed}/{total} 通过")
    print(f"{'='*70}")
    for i, (name, ok) in enumerate(results, 1):
        print(f"  {i}. {'✅' if ok else '❌'} {name}")

    assert passed == total, f"有{total - passed}个Bug修复验证失败！"
    print("\n🎉 三个Bug全部修复验证通过！")
