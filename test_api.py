import requests
import json

BASE = "http://127.0.0.1:9505"

def p(label, data):
    print(f"\n{'='*10} {label} {'='*10}")
    print(json.dumps(data, ensure_ascii=False, indent=2))

# 1. 测试事项查询
r = requests.get(f"{BASE}/api/items")
p("事项列表", {"code": r.json()["code"], "count": len(r.json()["data"]), "names": [i["item_name"] for i in r.json()["data"]]})

# 2. 测试低保老人医保报销 - 特殊人群附加材料
payload = {"item_code":"MEDICAL_REIMBURSEMENT","elder_type":"low_income","is_agent":False,"submitted_materials":[]}
r = requests.post(f"{BASE}/api/verify", json=payload)
d = r.json()["data"]
p("低保老人医保报销(特殊人群)", {
    "is_pass": d["is_pass"],
    "缺件数": d["total_missing"],
    "特殊提示": d["special_notices"],
    "附加材料(低保证)": any("低保证" in m["name"] for m in d["missing_list"])
})

# 3. 生成更多测试数据用于统计
test_cases = [
    # 社保认证 - 缺身份证
    {"item_code":"SOCIAL_SECURITY_VERIFY","elder_type":"special_elder","is_agent":False,
     "submitted_materials":[{"category":"bank_card","name":"养老金银行卡","has_original":True}]},
    # 银行卡挂失 - 社区工作人员代办
    {"item_code":"BANK_CARD_REPORT_LOSS","elder_type":"local_resident","is_agent":True,"agent_relation":"community_staff",
     "submitted_materials":[{"category":"id_card","name":"居民身份证","has_original":True,"copy_count":1}]},
    # 住院登记 - 残疾人
    {"item_code":"HOSPITAL_REGISTRATION","elder_type":"disabled","is_agent":True,"agent_relation":"spouse",
     "submitted_materials":[]},
    # 医保报销 - 子女代办 - 通过（补齐所有材料）
    {"item_code":"MEDICAL_REIMBURSEMENT","elder_type":"local_resident","is_agent":True,"agent_relation":"child",
     "submitted_materials":[
         {"category":"id_card","name":"居民身份证","has_original":True,"copy_count":1},
         {"category":"medical_card","name":"医保卡/社保卡","has_original":True},
         {"category":"medical_record","name":"医疗费用发票","has_original":True},
         {"category":"medical_record","name":"住院/门诊病历","copy_count":1},
         {"category":"medical_record","name":"费用明细清单","has_original":True},
         {"category":"id_card","name":"代办人身份证","has_original":True,"copy_count":1},
         {"category":"authorization_letter","name":"授权委托书","has_original":True}
     ]},
    # 社保认证 - 照片规格不符(2寸 vs 1寸)
    {"item_code":"SOCIAL_SECURITY_VERIFY","elder_type":"local_resident","is_agent":True,"agent_relation":"other_relative",
     "submitted_materials":[
         {"category":"id_card","name":"居民身份证","has_original":True},
         {"category":"bank_card","name":"养老金银行卡","has_original":True},
         {"category":"photo","name":"近期免冠照片","photo_spec":"2inch","has_original":True}
     ]},
    # 社保认证 - 社区代办 - 手持报纸生活照
    {"item_code":"SOCIAL_SECURITY_VERIFY","elder_type":"special_elder","is_agent":True,"agent_relation":"community_staff",
     "submitted_materials":[]},
    # 住院登记 - 通过
    {"item_code":"HOSPITAL_REGISTRATION","elder_type":"local_resident","is_agent":False,
     "submitted_materials":[
         {"category":"id_card","name":"居民身份证","has_original":True,"copy_count":1},
         {"category":"medical_card","name":"医保卡/社保卡","has_original":True},
         {"category":"hospital_cert","name":"入院通知书","has_original":True}
     ]},
]
for i, tc in enumerate(test_cases):
    r = requests.post(f"{BASE}/api/verify", json=tc)
    print(f"测试用例{i+3}: item={tc['item_code']} agent={tc.get('agent_relation','本人')} pass={r.json()['data']['is_pass']} 缺件={r.json()['data']['total_missing']}")
    # 记录补齐尝试
    vid = r.json()["data"]["verification_id"]
    if vid:
        mb = r.json()["data"]["total_missing"]
        requests.post(f"{BASE}/api/verify/makeup", params={"verification_id":vid,"missing_before":mb,"missing_after":max(mb-2,0),"attempt_no":1})

# 4. 测试历史查询
r = requests.get(f"{BASE}/api/history", params={"limit": 5})
hist = r.json()["data"]
p("历史查询(最近5条)", {"count": len(hist), "记录": [{"id":h["id"],"事项":h["item_name"],"是否通过":h["is_pass"],"缺件数":h["missing_count"]} for h in hist]})

# 5. 测试历史详情
if hist:
    r = requests.get(f"{BASE}/api/history/{hist[0]['id']}")
    d = r.json()["data"]
    p(f"历史详情(id={hist[0]['id']})", {
        "基本信息": d["record"]["item_name"],
        "缺件数": d["record"]["missing_count"],
        "缺件明细数量": len(d["missing_details"]),
        "缺件名称": [m["name"] for m in d["missing_details"]][:5]
    })

# 6. 测试综合统计
r = requests.get(f"{BASE}/api/stats/overall")
d = r.json()["data"]
p("综合统计看板", {
    "总查询数": d["total_queries"],
    "整体缺件率": f"{d['overall_miss_rate']*100:.1f}%",
    "平均补齐次数": d["avg_make_up_count"],
    "高频缺件事项TOP": [{"事项":i["item_name"],"缺件率":f"{i['miss_rate']*100:.1f}%","查询数":i["total_queries"]} for i in d["top_items"][:3]],
    "高频错误材料TOP": [{"材料":m["name"],"出现次数":m["miss_count"]} for m in d["top_materials"][:5]],
    "代办分布": [{"关系":a["agent_relation"],"人次":a["count"],"占比":f"{a['ratio']*100:.1f}%"} for a in d["agent_distribution"]]
})

# 7. 测试细分统计接口
print("\n=== 独立统计接口测试 ===")
print("事项缺件率排行:", requests.get(f"{BASE}/api/stats/miss-rate", params={"limit":3}).json()["message"])
print("高频错误材料:", requests.get(f"{BASE}/api/stats/top-materials", params={"limit":3}).json()["message"])
print("代办场景分布:", requests.get(f"{BASE}/api/stats/agent-distribution").json()["message"])
print("补齐次数统计:", requests.get(f"{BASE}/api/stats/makeup-summary").json()["data"]["interpretation"])

# 8. 参数错误 - 测试统一错误格式
r = requests.post(f"{BASE}/api/verify", json={"item_code":"INVALID"})
p("参数错误场景(404)", {"code": r.json()["code"], "message": r.json()["message"][:30], "data": r.json()["data"]})

print("\n✅ 所有接口测试完成!")
