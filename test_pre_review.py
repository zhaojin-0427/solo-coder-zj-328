import requests
import json
import time

BASE = "http://127.0.0.1:9505"


def p(label, data):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def assert_resp(label, resp, check_code=True):
    d = resp.json()
    print(f"[{label}] code={d.get('code')}, message={d.get('message', '')[:60]}")
    if check_code:
        assert d.get("code") == 0, f"接口返回错误: code={d.get('code')}, msg={d.get('message')}"
    return d


results = []


def test_case(name, fn):
    print(f"\n{'▶'*30}\n测试场景: {name}\n{'▶'*30}")
    try:
        ok = fn()
        results.append((name, ok))
        print(f"◀ 结果: {'✅ 通过' if ok else '❌ 失败'}")
        return ok
    except Exception as e:
        print(f"◀ 结果: ❌ 异常 - {str(e)}")
        import traceback
        traceback.print_exc()
        results.append((name, False))
        return False


test_elder = {
    "name": "张大爷",
    "id_card": "110101194501011234",
    "phone": "13800138001"
}

test_elder_dup = {
    "name": "张大爷",
    "id_card": "110101194501011234",
    "phone": "13800138001"
}

test_elder2 = {
    "name": "李奶奶",
    "id_card": "110101194802024321",
    "phone": "13900139002"
}


full_med_agent_materials = [
    {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
    {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
    {"category": "medical_record", "name": "医疗费用发票", "has_original": True},
    {"category": "medical_record", "name": "住院/门诊病历", "has_original": False, "copy_count": 1},
    {"category": "medical_record", "name": "费用明细清单", "has_original": True},
    {"category": "id_card", "name": "代办人身份证", "has_original": True, "copy_count": 1},
    {"category": "authorization_letter", "name": "授权委托书", "has_original": True}
]

partial_med_materials = [
    {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
    {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
]


def test_1_submit_pass():
    payload = {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "elder_id_card": test_elder2["id_card"],
        "elder_name": test_elder2["name"],
        "is_agent": True,
        "agent_relation": "child",
        "agent_name": "李小军",
        "contact_phone": test_elder2["phone"],
        "submitted_materials": full_med_agent_materials,
        "expected_window": "medical_window",
        "appointment_date": "2026-06-25",
        "remarks": "提前预审，方便现场办理"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    d = assert_resp("提交预审-完整材料", r)
    data = d["data"]
    wo = data["work_order"]

    checks = [
        ("is_pass=True", wo["is_pass"] == True),
        ("total_missing=0", wo["total_missing"] == 0),
        ("有工单号", len(wo["work_order_no"]) > 5),
        ("有风险等级", wo["risk_level"] in ("low", "medium", "high", "critical")),
        ("含一次性告知", len(wo["one_time_notice"]) > 50),
        ("有截止时间", "suggestion_deadline" in wo),
        ("有窗口注意事项", len(wo["window_notes"]) >= 1),
        ("有可打印摘要", "check_summary" in data and data["check_summary"]["work_order_no"] == wo["work_order_no"]),
        ("重复预审标记为false", wo["is_duplicate"] == False),
        ("补充进度100%", data["supplement_progress"]["completion_percent"] == 100),
        ("有缺件清单", "missing_list" in data and isinstance(data["missing_list"], list)),
        ("有已备材料", "ready_materials" in data and len(data["ready_materials"]) > 0),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_2_submit_missing():
    payload = {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "low_income",
        "elder_id_card": test_elder["id_card"],
        "elder_name": test_elder["name"],
        "is_agent": False,
        "contact_phone": test_elder["phone"],
        "submitted_materials": partial_med_materials,
        "appointment_date": "2026-06-22"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    d = assert_resp("提交预审-缺件+低保", r)
    data = d["data"]
    wo = data["work_order"]

    checks = [
        ("is_pass=False", wo["is_pass"] == False),
        ("total_missing>0", wo["total_missing"] > 0),
        ("缺件清单匹配", len(data["missing_list"]) == wo["total_missing"]),
        ("低保-风险等级较高", wo["risk_level"] in ("medium", "high", "critical")),
        ("一次性告知含低保老人", "低保" in wo["one_time_notice"]),
        ("一次性告知含缺件项", any(m["name"] in wo["one_time_notice"] for m in data["missing_list"])),
        ("可打印摘要含缺件标记", data["check_summary"]["total_missing"] == wo["total_missing"]),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_3_duplicate_detection():
    payload = {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "low_income",
        "elder_id_card": test_elder_dup["id_card"],
        "elder_name": test_elder_dup["name"],
        "is_agent": False,
        "contact_phone": test_elder_dup["phone"],
        "submitted_materials": partial_med_materials,
        "appointment_date": "2026-06-22"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    d = assert_resp("提交预审-重复检测(同老人同事项7天内)", r)
    data = d["data"]
    wo = data["work_order"]

    checks = [
        ("is_duplicate=True", wo["is_duplicate"] == True),
        ("有关联原始工单ID", wo["linked_original_id"] is not None),
        ("返回linked_original信息", data.get("linked_original") is not None and "work_order_no" in data["linked_original"]),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_4_order_detail():
    r_list = requests.get(f"{BASE}/api/pre-review/list", params={"page": 1, "page_size": 1})
    d_list = assert_resp("获取列表-取第一个ID", r_list)
    items = d_list["data"]["items"]
    if not items:
        print("  ❌ 无工单数据")
        return False
    oid = items[0]["id"]

    r = requests.get(f"{BASE}/api/pre-review/{oid}")
    d = assert_resp(f"获取工单详情 id={oid}", r)
    data = d["data"]

    checks = [
        ("order字段存在", "order" in data),
        ("missing_list存在", isinstance(data.get("missing_list"), list)),
        ("ready_materials存在", isinstance(data.get("ready_materials"), list)),
        ("check_summary可打印", "check_summary" in data and "materials" in data["check_summary"]),
        ("关联工单存在", "linked_orders" in data and isinstance(data["linked_orders"], list)),
        ("补齐进度存在", "supplement_progress" in data and "completion_percent" in data["supplement_progress"]),
        ("重复缺件原因存在", "repeated_missing_reasons" in data and isinstance(data["repeated_missing_reasons"], list)),
        ("告知记录存在", "notice_records" in data and len(data["notice_records"]) >= 1),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_5_list_filters():
    r1 = requests.get(f"{BASE}/api/pre-review/list", params={"item_code": "MEDICAL_REIMBURSEMENT"})
    d1 = assert_resp("筛选-按事项", r1)
    all_med = all(i["item_code"] == "MEDICAL_REIMBURSEMENT" for i in d1["data"]["items"])
    total1 = d1["data"]["total"]

    r2 = requests.get(f"{BASE}/api/pre-review/list", params={"is_duplicate": True})
    d2 = assert_resp("筛选-按重复预审", r2)
    all_dup = all(i["is_duplicate"] == True for i in d2["data"]["items"])
    total2 = d2["data"]["total"]

    r3 = requests.get(f"{BASE}/api/pre-review/list", params={"contact_phone": test_elder["phone"]})
    d3 = assert_resp("筛选-按联系电话", r3)
    total3 = d3["data"]["total"]

    r4 = requests.get(f"{BASE}/api/pre-review/list", params={"expected_window": "medical_window"})
    d4 = assert_resp("筛选-按窗口", r4)
    total4 = d4["data"]["total"]

    r5 = requests.get(f"{BASE}/api/pre-review/list", params={"page": 1, "page_size": 2})
    d5 = assert_resp("筛选-分页(每页2条)", r5)
    page_ok = len(d5["data"]["items"]) <= 2 and d5["data"]["page_size"] == 2

    checks = [
        ("事项筛选正确", all_med),
        (f"重复筛选数量正确 ({total2})", all_dup and total2 >= 1),
        (f"电话筛选返回{total3}条", total3 >= 1),
        (f"窗口筛选返回{total4}条", total4 >= 0),
        ("分页正确", page_ok),
        (f"总数>0 ({total1})", total1 > 0),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_6_status_transition():
    r_list = requests.get(f"{BASE}/api/pre-review/list", params={"status": "pending", "page_size": 1})
    d_list = r_list.json()["data"]
    target = None
    if d_list["items"]:
        target = d_list["items"][0]
    else:
        r_all = requests.get(f"{BASE}/api/pre-review/list", params={"page_size": 1})
        items = r_all.json()["data"]["items"]
        if items:
            target = items[0]

    if not target:
        print("  ⚠️ 无可流转工单，跳过状态流转测试")
        return True

    oid = target["id"]
    payload = {
        "status": "in_review",
        "reviewer": "王审核",
        "review_remark": "初审中"
    }
    r = requests.put(f"{BASE}/api/pre-review/{oid}/status", json=payload)
    d = assert_resp(f"工单{oid} pending→in_review", r)
    wo1 = d["data"]
    st1_ok = wo1["status"] == "in_review"

    payload2 = {
        "status": "supplementing",
        "reviewer": "王审核",
        "review_remark": "需补齐缺件"
    }
    r2 = requests.put(f"{BASE}/api/pre-review/{oid}/status", json=payload2)
    d2 = assert_resp(f"工单{oid} in_review→supplementing", r2)
    wo2 = d2["data"]
    st2_ok = wo2["status"] == "supplementing"

    payload3 = {
        "status": "passed",
        "reviewer": "王审核",
        "review_remark": "材料已补齐"
    }
    r3 = requests.put(f"{BASE}/api/pre-review/{oid}/status", json=payload3)
    d3 = assert_resp(f"工单{oid} supplementing→passed", r3)
    wo3 = d3["data"]
    st3_ok = wo3["status"] == "passed"

    payload_bad = {
        "status": "pending",
        "reviewer": "王审核"
    }
    r_bad = requests.put(f"{BASE}/api/pre-review/{oid}/status", json=payload_bad)
    d_bad = r_bad.json()
    illegal_ok = d_bad.get("code") != 0 and "不合法" in d_bad.get("message", "")

    checks = [
        ("pending→in_review 成功", st1_ok),
        ("in_review→supplementing 成功", st2_ok),
        ("supplementing→passed 成功", st3_ok),
        ("passed→pending 非法流转被拒绝", illegal_ok),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_7_supplement_review():
    payload = {
        "item_code": "BANK_CARD_REPORT_LOSS",
        "elder_type": "local_resident",
        "elder_id_card": "110101194003038888",
        "elder_name": "赵挂失",
        "is_agent": True,
        "agent_relation": "child",
        "agent_name": "赵小军",
        "contact_phone": "13600136003",
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 2},
        ],
        "expected_window": "banking_window"
    }
    r = requests.post(f"{BASE}/api/pre-review", json=payload)
    d = assert_resp("先创建银行卡挂失缺件工单", r)
    oid = d["data"]["work_order"]["id"]
    missing_before = d["data"]["work_order"]["total_missing"]
    print(f"  创建成功，工单id={oid}，缺件{missing_before}项")

    payload_sup = {
        "work_order_id": oid,
        "reviewer": "陈复核",
        "supplemented_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 2},
            {"category": "bank_card", "name": "挂失银行卡卡号", "has_original": False},
        ],
        "review_result": False,
        "review_remark": "卡号已补，但还缺代办人身份证和公证委托书"
    }
    r2 = requests.post(f"{BASE}/api/pre-review/supplement-review", json=payload_sup)
    d2 = assert_resp("补齐复核-部分补齐", r2)
    data2 = d2["data"]

    ok_1 = data2["missing_before"] == missing_before
    ok_2 = data2["missing_after"] < missing_before
    ok_3 = "supplement_record" in data2

    payload_all = {
        "work_order_id": oid,
        "reviewer": "陈复核",
        "supplemented_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 2},
            {"category": "bank_card", "name": "挂失银行卡卡号", "has_original": False},
            {"category": "id_card", "name": "代办人身份证", "has_original": True, "copy_count": 2},
            {"category": "authorization_letter", "name": "公证委托书", "has_original": True},
            {"category": "household_register", "name": "关系证明", "has_original": True, "copy_count": 1},
        ],
        "review_result": True,
        "review_remark": "所有材料已齐全"
    }
    r3 = requests.post(f"{BASE}/api/pre-review/supplement-review", json=payload_all)
    d3 = assert_resp("补齐复核-全部补齐通过", r3)
    data3 = d3["data"]
    ok_4 = data3["review_passed"] == True
    ok_5 = data3["order"]["status"] == "passed"

    r_hist = requests.get(f"{BASE}/api/pre-review/{oid}/supplement-history")
    d_hist = assert_resp("查询补齐记录", r_hist)
    ok_6 = len(d_hist["data"]["records"]) >= 2

    checks = [
        ("复核前缺件数正确", ok_1),
        ("复核后缺件减少", ok_2),
        ("返回supplement_record", ok_3),
        ("全部补齐后review_passed=True", ok_4),
        ("全部补齐后状态=passed", ok_5),
        ("补齐历史记录>=2", ok_6),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_8_notice_records():
    r1 = requests.get(f"{BASE}/api/pre-review/notices/list", params={"limit": 10})
    d1 = assert_resp("查询所有告知记录", r1)
    total_all = d1["data"]["total"]

    r_list = requests.get(f"{BASE}/api/pre-review/list", params={"page_size": 1})
    items = r_list.json()["data"]["items"]
    if items:
        oid = items[0]["id"]
        r2 = requests.get(f"{BASE}/api/pre-review/{oid}/notices")
        d2 = assert_resp(f"查询工单{oid}的告知记录", r2)
        per_order = d2["data"]["total"]
        ok_per = per_order >= 1
    else:
        ok_per = True

    r3 = requests.get(f"{BASE}/api/pre-review/notices/list", params={"notice_method": "system", "limit": 10})
    d3 = assert_resp("按方式筛选(system)", r3)
    all_system = all(n["notice_method"] == "system" for n in d3["data"]["records"])

    checks = [
        (f"共{total_all}条告知记录", total_all >= 1),
        ("单工单告知记录>=1", ok_per),
        ("按方式筛选正确", all_system),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_9_duplicate_check_api():
    r = requests.get(f"{BASE}/api/pre-review/duplicate/check", params={
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_id_card": test_elder["id_card"],
        "contact_phone": test_elder["phone"],
        "days": 7
    })
    d = assert_resp("重复预审检查API", r)
    data = d["data"]

    checks = [
        ("返回is_duplicate字段", "is_duplicate" in data),
        ("返回duplicate_count", "duplicate_count" in data and isinstance(data["duplicate_count"], int)),
        ("返回duplicates列表", isinstance(data.get("duplicates"), list)),
        ("检测到重复(应>=1)", data["is_duplicate"] == True and data["duplicate_count"] >= 1),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_10_preview_stats_overall():
    r = requests.get(f"{BASE}/api/stats/pre-review/overall")
    d = assert_resp("预审综合统计", r)
    s = d["data"]

    checks = [
        ("total_orders", "total_orders" in s and s["total_orders"] >= 1),
        ("pass_rate通过率", 0 <= s.get("pass_rate", 0) <= 1),
        ("duplicate_rate重复率", "duplicate_rate" in s),
        ("avg_missing_count", isinstance(s.get("avg_missing_count"), (int, float))),
        ("expired_count超期数", isinstance(s.get("expired_count"), int)),
        ("item_avg_missing各事项缺件", isinstance(s.get("item_avg_missing"), list)),
        ("top_return_material_combos退回组合", isinstance(s.get("top_return_material_combos"), list)),
        ("window_pass_rates窗口通过率", isinstance(s.get("window_pass_rates"), list)),
    ]
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    return all(ok for _, ok in checks)


def test_11_all_sub_stats():
    cases = [
        ("预审通过率", "/api/stats/pre-review/pass-rate"),
        ("重复预审率", "/api/stats/pre-review/duplicate-rate"),
        ("各事项平均缺件", "/api/stats/pre-review/item-avg-missing"),
        ("超期未补齐", "/api/stats/pre-review/expired-summary"),
        ("最常退回材料组合", "/api/stats/pre-review/top-return-material-combos"),
    ]
    all_ok = True
    for name, path in cases:
        r = requests.get(f"{BASE}{path}")
        d = assert_resp(name, r)
        ok = d["code"] == 0
        all_ok = all_ok and ok
        print(f"  {'✅' if ok else '❌'} {name}: code={d.get('code')}")
    return all_ok


def test_12_uniform_response_structure():
    endpoints = [
        ("GET健康", "/health", {}),
        ("GET事项列表", "/api/items", {}),
        ("POST预审缺件", "/api/pre-review", {
            "json": {
                "item_code": "HOSPITAL_REGISTRATION",
                "elder_type": "local_resident",
                "elder_id_card": "110101195005057777",
                "elder_name": "孙住院",
                "is_agent": False,
                "contact_phone": "13700137004",
                "submitted_materials": []
            }
        }),
        ("参数错误400", "/api/pre-review", {"json": {"item_code": "X"}}),
    ]
    ok_all = True
    for label, path, kwargs in endpoints:
        if "json" in kwargs:
            r = requests.post(f"{BASE}{path}", json=kwargs["json"])
        else:
            r = requests.get(f"{BASE}{path}", **kwargs)
        body = r.json()
        has_code = "code" in body
        has_msg = "message" in body
        has_data = "data" in body
        ok = has_code and has_msg and has_data
        ok_all = ok_all and ok
        print(f"  {'✅' if ok else '❌'} {label}: code={body.get('code')} msg存在={has_msg} data存在={has_data}")
    return ok_all


def test_13_get_by_work_order_no():
    r_list = requests.get(f"{BASE}/api/pre-review/list", params={"page_size": 1})
    items = r_list.json()["data"]["items"]
    if not items:
        print("  ⚠️ 无工单，跳过")
        return True
    won = items[0]["work_order_no"]
    r = requests.get(f"{BASE}/api/pre-review/no/{won}")
    d = assert_resp(f"按工单号查询 {won}", r)
    ok = d["data"]["order"]["work_order_no"] == won
    print(f"  {'✅' if ok else '❌'} 工单号匹配")
    return ok


if __name__ == "__main__":
    test_case("1. 提交预审-完整材料(通过)", test_1_submit_pass)
    test_case("2. 提交预审-低保+缺件(含一次性告知/摘要)", test_2_submit_missing)
    test_case("3. 重复预审识别(7天内同老人同事项)", test_3_duplicate_detection)
    test_case("4. 工单详情(含关联工单/补齐进度/重复缺件原因/告知记录)", test_4_order_detail)
    test_case("5. 工单列表筛选(事项/重复/电话/窗口/分页)", test_5_list_filters)
    test_case("6. 工单状态流转(合法性校验)", test_6_status_transition)
    test_case("7. 补齐材料复核(部分/全部+历史记录)", test_7_supplement_review)
    test_case("8. 一次性告知记录查询", test_8_notice_records)
    test_case("9. 重复预审检查API", test_9_duplicate_check_api)
    test_case("10. 预审综合统计(含所有9项指标)", test_10_preview_stats_overall)
    test_case("11. 5项独立预审统计子接口", test_11_all_sub_stats)
    test_case("12. 统一响应结构{code,message,data}", test_12_uniform_response_structure)
    test_case("13. 按工单号查询", test_13_get_by_work_order_no)

    print(f"\n\n{'='*70}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"🎯 预审工单功能测试汇总: {passed}/{total} 通过")
    print(f"{'='*70}")
    for i, (name, ok) in enumerate(results, 1):
        print(f"  {i:2d}. {'✅' if ok else '❌'} {name}")

    assert passed == total, f"有{total - passed}个测试场景未通过！"
    print("\n🎉 所有预审工单功能测试通过！")
