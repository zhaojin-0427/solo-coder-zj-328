import requests
import json

BASE = "http://127.0.0.1:9505"

def test_case(name, payload, checks):
    print(f"\n{'='*20}\n测试场景: {name}\n{'='*20}")
    r = requests.post(f"{BASE}/api/verify", json=payload)
    d = r.json()["data"]
    missing_names = [m["name"] for m in d["missing_list"]]
    print(f"校验结果: {'通过' if d['is_pass'] else '未通过'}")
    print(f"缺件数: {d['total_missing']}")
    print(f"缺件清单: {missing_names}")
    print(f"补充说明: {d['supplement_notes'][:2]}")
    print(f"特殊提示: {d['special_notices']}")
    
    all_ok = True
    for check_name, check_fn in checks.items():
        try:
            result = check_fn(d)
            print(f"  ✅ {check_name}: {'通过' if result else '失败'}")
            if not result:
                all_ok = False
        except Exception as e:
            print(f"  ❌ {check_name}: 异常 {e}")
            all_ok = False
    return all_ok

results = []

# ============= 修复1: 医保报销同类别多材料匹配 =============
results.append(test_case(
    "医保报销 - 只交了身份证，应提示病历+费用明细都缺",
    {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "is_agent": False,
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1}
        ]
    },
    {
        "提示缺少住院/门诊病历": lambda d: any("住院/门诊病历" in m["name"] and m["missing_type"]=="material_missing" for m in d["missing_list"]),
        "提示缺少费用明细清单": lambda d: any("费用明细清单" in m["name"] and m["missing_type"]=="material_missing" for m in d["missing_list"]),
        "提示缺少医疗费用发票": lambda d: any("医疗费用发票" in m["name"] and m["missing_type"]=="material_missing" for m in d["missing_list"]),
        "不应该只提示复印件不足": lambda d: not (len([m for m in d["missing_list"] if "复印件" in m["name"]]) == d["total_missing"]),
    }
))

# ============= 修复2: 子女代办未提交代办人身份证应提示缺件 =============
results.append(test_case(
    "子女代办医保报销 - 只交了老人身份证，应提示缺代办人身份证",
    {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "is_agent": True,
        "agent_relation": "child",
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
            {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
            {"category": "medical_record", "name": "医疗费用发票", "has_original": True},
            {"category": "medical_record", "name": "住院/门诊病历", "has_original": False, "copy_count": 1},
            {"category": "medical_record", "name": "费用明细清单", "has_original": True},
            {"category": "authorization_letter", "name": "授权委托书", "has_original": True}
        ]
    },
    {
        "提示缺少代办人身份证": lambda d: any("代办人身份证" in m["name"] for m in d["missing_list"]),
        "提示缺少代办人身份证复印件": lambda d: any("代办人身份证复印件" in m["name"] for m in d["missing_list"]),
    }
))

# ============= 修复3: 低保老人文案应显示中文 =============
results.append(test_case(
    "低保老人医保报销 - 特殊提示文案应显示中文",
    {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "low_income",
        "is_agent": False,
        "submitted_materials": []
    },
    {
        "补充说明含'低保老人'而非'low_income'": lambda d: any("低保老人" in n for n in d["supplement_notes"]),
        "补充说明不含'low_income'": lambda d: not any("low_income" in n for n in d["supplement_notes"]),
        "特殊提示含低保证明相关": lambda d: any("低保证明" in n for n in d["special_notices"]),
    }
))

# ============= 回归测试: 同类别多材料正确匹配 =============
results.append(test_case(
    "医保报销 - 完整材料，应通过（身份证+医保卡+3个医疗材料）",
    {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "is_agent": False,
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
            {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
            {"category": "medical_record", "name": "医疗费用发票", "has_original": True},
            {"category": "medical_record", "name": "住院/门诊病历", "has_original": False, "copy_count": 1},
            {"category": "medical_record", "name": "费用明细清单", "has_original": True}
        ]
    },
    {
        "校验通过": lambda d: d["is_pass"] == True,
        "缺件数为0": lambda d: d["total_missing"] == 0,
    }
))

# ============= 回归测试: 子女代办完整材料 =============
results.append(test_case(
    "子女代办医保报销 - 完整材料含代办人证+授权书",
    {
        "item_code": "MEDICAL_REIMBURSEMENT",
        "elder_type": "local_resident",
        "is_agent": True,
        "agent_relation": "child",
        "submitted_materials": [
            {"category": "id_card", "name": "居民身份证", "has_original": True, "copy_count": 1},
            {"category": "medical_card", "name": "医保卡/社保卡", "has_original": True},
            {"category": "medical_record", "name": "医疗费用发票", "has_original": True},
            {"category": "medical_record", "name": "住院/门诊病历", "has_original": False, "copy_count": 1},
            {"category": "medical_record", "name": "费用明细清单", "has_original": True},
            {"category": "id_card", "name": "代办人身份证", "has_original": True, "copy_count": 1},
            {"category": "authorization_letter", "name": "授权委托书", "has_original": True}
        ]
    },
    {
        "校验通过": lambda d: d["is_pass"] == True,
        "缺件数为0": lambda d: d["total_missing"] == 0,
        "不包含代办人身份证缺失": lambda d: not any("代办人身份证" in m["name"] for m in d["missing_list"]),
    }
))

# ============= 测试结果汇总 =============
print(f"\n\n{'='*50}")
print(f"测试结果: {sum(results)}/{len(results)} 通过")
print(f"{'='*50}")
for i, r in enumerate(results):
    print(f"  场景{i+1}: {'✅ 通过' if r else '❌ 失败'}")

assert all(results), "部分测试未通过，请修复"
print("\n🎉 所有 Bug 修复验证通过！")
