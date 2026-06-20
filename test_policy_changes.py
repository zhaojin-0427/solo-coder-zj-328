import sys
import os
if os.path.exists('elder_service.db'):
    os.remove('elder_service.db')

sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

print('=' * 70)
print('政策变更订阅与影响预警 功能测试')
print('=' * 70)

all_passed = True

print('\n=== 准备基础数据 ===')
resp = client.post('/api/verify', json={
    'item_code': 'MEDICAL_REIMBURSEMENT',
    'elder_type': 'local_resident',
    'is_agent': False,
    'submitted_materials': []
})
verify_id = resp.json()['data']['verification_id']
print(f'校验记录ID: {verify_id}')

resp = client.post('/api/pre-review', json={
    'item_code': 'MEDICAL_REIMBURSEMENT',
    'elder_type': 'local_resident',
    'elder_id_card': '110101194001011234',
    'elder_name': '张三',
    'is_agent': True,
    'agent_relation': 'child',
    'agent_name': '张小明',
    'contact_phone': '13800138000',
    'submitted_materials': [],
    'expected_window': 'medical_window',
    'appointment_date': '2026-06-21'
})
pr_order_id = resp.json()['data']['work_order']['id']
print(f'预审工单ID: {pr_order_id}')

resp = client.post('/api/accompany/companions', json={
    'name': '李社工',
    'companion_type': 'social_worker',
    'community': '阳光社区',
    'phone': '13900139000',
    'available_windows': ['medical_window'],
    'eligible_items': ['MEDICAL_REIMBURSEMENT'],
    'skills': ['手语翻译', '轮椅协助']
})

resp = client.post('/api/accompany/appointments', json={
    'elder_name': '张三',
    'elder_type': 'local_resident',
    'item_code': 'MEDICAL_REIMBURSEMENT',
    'mobility_level': 'need_assist',
    'is_living_alone': True,
    'accompany_demand_type': 'full_accompany',
    'expected_date': '2026-06-21',
    'community': '阳光社区',
    'contact_phone': '13800138000',
    'pre_review_order_id': pr_order_id,
    'expected_window': 'medical_window'
})
acc_appointment_id = resp.json()['data']['appointment']['id']
print(f'陪同预约ID: {acc_appointment_id}')

# ============================================
# 测试1: 创建政策变更
# ============================================
print('\n' + '=' * 70)
print('测试 1: 创建政策变更记录')
print('=' * 70)

resp = client.post('/api/policy/changes', json={
    'title': '医保报销材料调整通知',
    'applicable_items': ['MEDICAL_REIMBURSEMENT'],
    'applicable_windows': ['medical_window'],
    'impacted_materials': ['身份证', '医保卡', '医疗费用发票'],
    'impacted_elder_types': ['local_resident', 'remote_resident'],
    'effective_date': '2026-06-20',
    'expiry_date': '2026-12-31',
    'policy_source': '市医保局 2026年第3号文件',
    'risk_level': 'high',
    'handling_suggestion': '请提前准备好新增材料，建议重新进行预审',
    'impact_types': ['material_add', 'material_modify'],
    'description': '自2026年6月20日起，医保报销需额外提供费用明细单和本人银行卡复印件',
    'added_materials': [
        {'name': '费用明细单', 'category': 'medical_record', 'required': True},
        {'name': '银行卡复印件', 'category': 'bank_card', 'required': True}
    ],
    'removed_materials': [
        {'name': '旧版医保手册', 'category': 'medical_card'}
    ],
    'rejection_reasons': [
        '缺少费用明细单将不予受理',
        '未提供银行卡复印件无法完成报销打款'
    ],
    'status': 'draft'
})

if resp.status_code == 200:
    data = resp.json()['data']
    policy_id = data['id']
    print(f'  ✅ 创建成功，政策ID: {policy_id}')
    print(f'     标题: {data["title"]}')
    print(f'     风险等级: {data["risk_level"]}')
    print(f'     状态: {data["status"]}')
else:
    print(f'  ❌ 创建失败! Status={resp.status_code}, {resp.text}')
    all_passed = False
    policy_id = None

# ============================================
# 测试2: 政策变更列表查询
# ============================================
print('\n' + '=' * 70)
print('测试 2: 政策变更列表查询与筛选')
print('=' * 70)

resp = client.get('/api/policy/changes/list')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 列表查询成功，共 {data["total"]} 条')
else:
    print(f'  ❌ 列表查询失败! Status={resp.status_code}')
    all_passed = False

resp = client.get('/api/policy/changes/list?risk_level=high')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 按风险等级筛选(high): {data["total"]} 条')
else:
    print(f'  ❌ 按风险等级筛选失败!')
    all_passed = False

resp = client.get('/api/policy/changes/list?item_code=MEDICAL_REIMBURSEMENT')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 按事项筛选(MEDICAL_REIMBURSEMENT): {data["total"]} 条')
else:
    print(f'  ❌ 按事项筛选失败!')
    all_passed = False

resp = client.get('/api/policy/changes/list?keyword=医保')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 关键词搜索(医保): {data["total"]} 条')
else:
    print(f'  ❌ 关键词搜索失败!')
    all_passed = False

# ============================================
# 测试3: 政策变更详情查询
# ============================================
print('\n' + '=' * 70)
print('测试 3: 政策变更详情查询')
print('=' * 70)

if policy_id:
    resp = client.get(f'/api/policy/changes/{policy_id}')
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 详情查询成功')
        print(f'     标题: {data["policy"]["title"]}')
        print(f'     适用事项: {data["policy"]["applicable_items"]}')
        print(f'     新增材料数: {len(data["policy"]["added_materials"])}')
        print(f'     预警总数: {data["warning_count"]}')
    else:
        print(f'  ❌ 详情查询失败! Status={resp.status_code}')
        all_passed = False

    resp = client.get('/api/policy/changes/99999')
    if resp.status_code == 404:
        print(f'  ✅ 不存在的政策ID返回 404')
    else:
        print(f'  ❌ 不存在的政策ID未正确返回 404!')
        all_passed = False

# ============================================
# 测试4: 更新政策变更
# ============================================
print('\n' + '=' * 70)
print('测试 4: 更新政策变更信息')
print('=' * 70)

if policy_id:
    resp = client.put(f'/api/policy/changes/{policy_id}', json={
        'description': '更新后的详细描述：医保报销政策重大调整',
        'handling_suggestion': '更新后的处理建议：请务必提前预约预审'
    })
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 更新成功')
        print(f'     描述: {data["description"][:30]}...')
    else:
        print(f'  ❌ 更新失败! Status={resp.status_code}, {resp.text}')
        all_passed = False

# ============================================
# 测试5: 启停政策状态
# ============================================
print('\n' + '=' * 70)
print('测试 5: 政策变更启停状态')
print('=' * 70)

if policy_id:
    resp = client.put(f'/api/policy/changes/{policy_id}/status?status=active')
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 状态已更新为: {data["status"]}')
    else:
        print(f'  ❌ 状态更新失败! Status={resp.status_code}, {resp.text}')
        all_passed = False

# ============================================
# 测试6: 扫描影响范围并生成预警
# ============================================
print('\n' + '=' * 70)
print('测试 6: 扫描政策变更影响范围并生成预警')
print('=' * 70)

if policy_id:
    resp = client.post(f'/api/policy/changes/{policy_id}/scan')
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 影响范围扫描完成')
        print(f'     新增预警数: {data["new_warnings_count"]}')
        print(f'     总受影响数: {data["total_affected_count"]}')
        print(f'     校验记录受影响: {data["scanned_sources"]["verify_records"]["count"]} 条')
        print(f'     预审工单受影响: {data["scanned_sources"]["pre_review_orders"]["count"]} 条')
        print(f'     陪同预约受影响: {data["scanned_sources"]["accompany_appointments"]["count"]} 条')
        print(f'     异常处置单受影响: {data["scanned_sources"]["exception_orders"]["count"]} 条')
        print(f'     服务事项受影响: {data["scanned_sources"]["service_items"]["count"]} 条')
    else:
        print(f'  ❌ 扫描失败! Status={resp.status_code}, {resp.text}')
        all_passed = False

# ============================================
# 测试7: 预警列表查询与筛选
# ============================================
print('\n' + '=' * 70)
print('测试 7: 预警列表查询与筛选')
print('=' * 70)

resp = client.get('/api/policy/warnings/list')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 预警列表查询成功，共 {data["total"]} 条')
else:
    print(f'  ❌ 预警列表查询失败! Status={resp.status_code}')
    all_passed = False

resp = client.get('/api/policy/warnings/list?source_type=pre_review_order')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 按来源类型筛选(pre_review_order): {data["total"]} 条')
else:
    print(f'  ❌ 按来源类型筛选失败!')
    all_passed = False

resp = client.get('/api/policy/warnings/list?item_code=MEDICAL_REIMBURSEMENT')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 按事项筛选: {data["total"]} 条')
else:
    print(f'  ❌ 按事项筛选失败!')
    all_passed = False

resp = client.get('/api/policy/warnings/list?risk_level=high')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 按风险等级筛选(high): {data["total"]} 条')
else:
    print(f'  ❌ 按风险等级筛选失败!')
    all_passed = False

resp = client.get('/api/policy/warnings/list?status=unconfirmed')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 按状态筛选(unconfirmed): {data["total"]} 条')
else:
    print(f'  ❌ 按状态筛选失败!')
    all_passed = False

# ============================================
# 测试8: 预警详情查询
# ============================================
print('\n' + '=' * 70)
print('测试 8: 预警详情查询')
print('=' * 70)

resp = client.get('/api/policy/warnings/list')
warnings = resp.json()['data']['items']
if warnings:
    warning_id = warnings[0]['id']
    resp = client.get(f'/api/policy/warnings/{warning_id}')
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 预警详情查询成功')
        print(f'     预警ID: {data["warning"]["id"]}')
        print(f'     来源类型: {data["warning"]["source_type"]}')
        print(f'     风险等级: {data["warning"]["risk_level"]}')
        print(f'     状态: {data["warning"]["status"]}')
        print(f'     状态历史数: {len(data["status_history"])}')
    else:
        print(f'  ❌ 预警详情查询失败!')
        all_passed = False
else:
    print(f'  ⚠️  暂无预警数据可测试')

# ============================================
# 测试9: 确认预警
# ============================================
print('\n' + '=' * 70)
print('测试 9: 确认预警')
print('=' * 70)

if warnings:
    warning_id = warnings[0]['id']
    resp = client.post(f'/api/policy/warnings/{warning_id}/confirm', json={
        'confirmed_by': '王工作人员',
        'confirm_remark': '已通知相关老人和家属'
    })
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 预警确认成功')
        print(f'     状态: {data["status"]}')
        print(f'     确认人: {data["confirmed_by"]}')
    else:
        print(f'  ❌ 预警确认失败! Status={resp.status_code}, {resp.text}')
        all_passed = False

    resp = client.post(f'/api/policy/warnings/{warning_id}/confirm', json={
        'confirmed_by': '重复确认',
    })
    if resp.status_code == 400:
        print(f'  ✅ 重复确认返回 400 错误')
    else:
        print(f'  ❌ 重复确认未正确拒绝!')
        all_passed = False

# ============================================
# 测试10: 政策影响查询
# ============================================
print('\n' + '=' * 70)
print('测试 10: 按条件查询政策影响')
print('=' * 70)

resp = client.get('/api/policy/impact/query?item_code=MEDICAL_REIMBURSEMENT&elder_type=local_resident')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 政策影响查询成功')
    print(f'     是否受影响: {data["is_affected"]}')
    print(f'     受影响政策数: {len(data["affected_policies"])}')
    print(f'     新增材料数: {len(data["added_materials"])}')
    print(f'     废止材料数: {len(data["removed_materials"])}')
    print(f'     退回原因数: {len(data["rejection_reasons"])}')
    print(f'     建议重新预审: {data["need_re_preview"]}')
    print(f'     建议重新预约: {data["need_re_appointment"]}')
    if data["suggestions"]:
        print(f'     建议条数: {len(data["suggestions"])}')
else:
    print(f'  ❌ 政策影响查询失败! Status={resp.status_code}')
    all_passed = False

resp = client.get('/api/policy/impact/query?item_code=SOCIAL_SECURITY_AUTH&elder_type=local_resident')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 不受影响的事项查询: is_affected={data["is_affected"]}')
else:
    print(f'  ❌ 不受影响事项查询失败!')
    all_passed = False

# ============================================
# 测试11: 政策统计接口
# ============================================
print('\n' + '=' * 70)
print('测试 11: 政策变更统计接口')
print('=' * 70)

resp = client.get('/api/policy/stats/overall')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 综合统计查询成功')
    print(f'     政策变更总数: {data["total_policy_changes"]}')
    print(f'     生效政策数: {data["active_policy_count"]}')
    print(f'     预警总数: {data["total_warnings"]}')
    print(f'     已确认预警数: {data["confirmed_warnings"]}')
    print(f'     未确认高风险预警数: {data["unconfirmed_high_risk_warnings"]}')
    print(f'     事项影响排行数: {len(data["item_policy_impact_ranking"])}')
    print(f'     政策异常占比: {data["policy_exception_ratio"]}')
else:
    print(f'  ❌ 综合统计查询失败! Status={resp.status_code}')
    all_passed = False

resp = client.get('/api/policy/stats/item-ranking')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 事项影响排行查询成功，共 {data["total_items"]} 个事项')
else:
    print(f'  ❌ 事项影响排行查询失败!')
    all_passed = False

resp = client.get('/api/policy/stats/warning-summary')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 预警统计概览查询成功')
    print(f'     确认率: {data["confirm_rate_percent"]}')
else:
    print(f'  ❌ 预警统计概览查询失败!')
    all_passed = False

resp = client.get('/api/policy/stats/policy-exception-ratio')
if resp.status_code == 200:
    data = resp.json()['data']
    print(f'  ✅ 政策异常占比查询成功')
    print(f'     占比: {data["policy_exception_ratio_percent"]}')
else:
    print(f'  ❌ 政策异常占比查询失败!')
    all_passed = False

# ============================================
# 测试12: 删除政策变更
# ============================================
print('\n' + '=' * 70)
print('测试 12: 删除政策变更')
print('=' * 70)

if policy_id:
    resp = client.delete(f'/api/policy/changes/{policy_id}')
    if resp.status_code == 200:
        data = resp.json()['data']
        print(f'  ✅ 删除成功: {data["deleted"]}')
    else:
        print(f'  ❌ 删除失败! Status={resp.status_code}')
        all_passed = False

    resp = client.get(f'/api/policy/changes/{policy_id}')
    if resp.status_code == 404:
        print(f'  ✅ 删除后查询返回 404')
    else:
        print(f'  ❌ 删除后仍能查询到!')
        all_passed = False

# ============================================
# 测试13: 接口返回格式验证 (统一 {code, message, data})
# ============================================
print('\n' + '=' * 70)
print('测试 13: 统一返回格式验证')
print('=' * 70)

resp = client.post('/api/policy/changes', json={
    'title': '社保认证政策调整',
    'applicable_items': ['SOCIAL_SECURITY_AUTH'],
    'effective_date': '2026-07-01',
    'policy_source': '社保局通知',
    'risk_level': 'medium',
    'status': 'active'
})
if resp.status_code == 200:
    body = resp.json()
    has_code = 'code' in body
    has_message = 'message' in body
    has_data = 'data' in body
    if has_code and has_message and has_data and body['code'] == 0:
        print(f'  ✅ 返回格式正确: {{code, message, data}}')
        policy_id2 = body['data']['id']
    else:
        print(f'  ❌ 返回格式不正确! Keys: {list(body.keys())}')
        all_passed = False
else:
    print(f'  ❌ 请求失败! Status={resp.status_code}')
    all_passed = False

resp = client.get('/api/policy/changes/99999')
if resp.status_code == 404:
    body = resp.json()
    if 'code' in body and 'message' in body and 'data' in body:
        print(f'  ✅ 错误返回也保持统一格式')
    else:
        print(f'  ❌ 错误返回格式不正确!')
        all_passed = False

# ============================================
# 最终结论
# ============================================
print('\n' + '=' * 70)
if all_passed:
    print('✅ 所有政策变更功能测试通过!')
else:
    print('❌ 存在测试失败，请检查上面的错误!')
print('=' * 70)

sys.exit(0 if all_passed else 1)
