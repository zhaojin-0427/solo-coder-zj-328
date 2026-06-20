import sys
import os
if os.path.exists('elder_service.db'):
    os.remove('elder_service.db')

sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from main import app
import json

client = TestClient(app)

print('=' * 60)
print('BUG修复验证测试')
print('=' * 60)

# 先创建一些基础数据
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

all_passed = True

# ============================================
# BUG 1 测试: 异常关联不存在的来源记录
# ============================================
print('\n' + '=' * 60)
print('BUG 1 验证: 异常不能关联不存在的来源记录')
print('=' * 60)

test_cases = [
    ('verify_record', 99999, '材料校验记录'),
    ('pre_review_order', 99999, '预审工单'),
    ('accompany_appointment', 99999, '陪同预约单'),
]
for stype, sid, sname in test_cases:
    resp = client.post('/api/exceptions', json={
        'exception_type': 'window_reject',
        'source_type': stype,
        'source_id': sid,
        'reporter': '测试',
        'reporter_role': '工作人员',
        'description': '测试不存在的来源',
        'impact_completion': True
    })
    if resp.status_code == 404:
        print(f'  ✅ {sname} ID={sid}: 正确拒绝 (404)')
    else:
        print(f'  ❌ {sname} ID={sid}: 错误地允许创建! Status={resp.status_code}')
        all_passed = False

# ============================================
# BUG 3 测试: 优先级判定 (elder_unwell, elder_absent -> p1_urgent)
# ============================================
print('\n' + '=' * 60)
print('BUG 3 验证: 优先级判定')
print('=' * 60)

test_priority_cases = [
    ('elder_unwell', 'verify_record', verify_id, 'p1_urgent', '老人身体不适'),
    ('elder_absent', 'verify_record', verify_id, 'p1_urgent', '老人未到场'),
    ('window_reject', 'verify_record', verify_id, None, '窗口退回 (影响完成则升级到P1)'),
]
for etype, stype, sid, expected_priority, desc in test_priority_cases:
    resp = client.post('/api/exceptions', json={
        'exception_type': etype,
        'source_type': stype,
        'source_id': sid,
        'reporter': '测试',
        'reporter_role': '工作人员',
        'description': f'优先级测试 - {desc}',
        'impact_completion': True
    })
    if resp.status_code == 200:
        data = resp.json()['data']
        actual_priority = data['priority']
        exc_id = data['id']
        # 保存ID供后续测试使用
        if etype == 'window_reject':
            reusable_exc_id = exc_id
        if expected_priority is None:
            print(f'  ℹ️  {desc}: 优先级 {actual_priority} (impact_completion=True会升级，合理即可)')
        elif actual_priority == expected_priority:
            print(f'  ✅ {desc}: 优先级正确 {actual_priority}')
        else:
            print(f'  ❌ {desc}: 优先级错误! 期望 {expected_priority}, 实际 {actual_priority}')
            all_passed = False
    else:
        print(f'  ❌ {desc}: 创建失败 Status={resp.status_code}, {resp.text}')
        all_passed = False

# ============================================
# BUG 2 测试: closed 异常单不能被状态流转改回 pending
# ============================================
print('\n' + '=' * 60)
print('BUG 2 验证: 已关闭异常单状态校验')
print('=' * 60)

# 创建一个异常，走完流程到 closed
resp = client.post('/api/exceptions', json={
    'exception_type': 'material_invalid',
    'source_type': 'pre_review_order',
    'source_id': pr_order_id,
    'reporter': '测试',
    'reporter_role': '工作人员',
    'description': '状态流转测试',
    'impact_completion': True
})
closed_exc_id = resp.json()['data']['id']
print(f'  创建异常 ID={closed_exc_id}')

# 指派
client.post(f'/api/exceptions/{closed_exc_id}/assign', json={
    'responsible_role': 'window_staff',
    'responsible_person': '测试人员',
    'responsible_phone': '13900000000',
    'assigned_by': '系统',
})

# 追加处理记录
client.post(f'/api/exceptions/{closed_exc_id}/records', json={
    'exception_id': closed_exc_id,
    'processor': '测试人员',
    'action': '测试处理',
    'result': '处理完成',
})

# 改状态为 resolved
client.put(f'/api/exceptions/{closed_exc_id}/status', json={
    'status': 'resolved',
    'operator': '测试人员',
})

# 关闭
client.post(f'/api/exceptions/{closed_exc_id}/close', json={
    'closed_by': '系统',
    'close_remark': '测试关闭',
    'is_resolved': True,
})
print(f'  异常已关闭，当前状态为 closed')

# 尝试改回 pending
resp = client.put(f'/api/exceptions/{closed_exc_id}/status', json={
    'status': 'pending',
    'operator': '恶意操作',
})
if resp.status_code == 400:
    err_msg = resp.json().get("message", "无错误信息")
    print(f'  ✅ 改回 pending: 正确拒绝 (400), {err_msg}')
else:
    print(f'  ❌ 改回 pending: 错误地允许! Status={resp.status_code}')
    all_passed = False

# 尝试改为 in_progress
resp = client.put(f'/api/exceptions/{closed_exc_id}/status', json={
    'status': 'in_progress',
    'operator': '恶意操作',
})
if resp.status_code == 400:
    print(f'  ✅ 改为 in_progress: 正确拒绝 (400)')
else:
    print(f'  ❌ 改为 in_progress: 错误地允许! Status={resp.status_code}')
    all_passed = False

# 尝试再指派
resp = client.post(f'/api/exceptions/{closed_exc_id}/assign', json={
    'responsible_role': 'window_staff',
    'responsible_person': '新的人',
    'assigned_by': '系统',
})
if resp.status_code == 400:
    print(f'  ✅ 重新指派: 正确拒绝 (400)')
else:
    print(f'  ❌ 重新指派: 错误地允许! Status={resp.status_code}')
    all_passed = False

# 尝试追加处理记录
resp = client.post(f'/api/exceptions/{closed_exc_id}/records', json={
    'exception_id': closed_exc_id,
    'processor': '测试',
    'action': '追加',
    'result': '测试',
})
if resp.status_code == 400:
    print(f'  ✅ 追加处理记录: 正确拒绝 (400)')
else:
    print(f'  ❌ 追加处理记录: 错误地允许! Status={resp.status_code}')
    all_passed = False

# ============================================
# BUG 4 测试: 异常发生率不超过 100%
# ============================================
print('\n' + '=' * 60)
print('BUG 4 验证: 异常发生率/事项异常率 <= 100%')
print('=' * 60)

# 创建更多异常，确保异常数可能超过业务数
client.post('/api/exceptions', json={
    'exception_type': 'window_reject',
    'source_type': 'verify_record',
    'source_id': verify_id,
    'reporter': '测试',
    'reporter_role': '工作人员',
    'description': '测试异常率2',
    'impact_completion': True
})
client.post('/api/exceptions', json={
    'exception_type': 'supplement_fail',
    'source_type': 'verify_record',
    'source_id': verify_id,
    'reporter': '测试',
    'reporter_role': '工作人员',
    'description': '测试异常率3',
    'impact_completion': True
})
client.post('/api/exceptions', json={
    'exception_type': 'companion_late',
    'source_type': 'accompany_appointment',
    'source_id': acc_appointment_id,
    'reporter': '测试',
    'reporter_role': '工作人员',
    'description': '测试异常率4',
    'impact_completion': True
})
client.post('/api/exceptions', json={
    'exception_type': 'policy_changed',
    'source_type': 'pre_review_order',
    'source_id': pr_order_id,
    'reporter': '测试',
    'reporter_role': '工作人员',
    'description': '测试异常率5',
    'impact_completion': True
})

resp = client.get('/api/stats/exceptions/overall')
stats = resp.json()['data']

# 检查整体异常率
rate = stats['exception_rate']
if 0 <= rate <= 1.0:
    print(f'  ✅ 整体异常率: {rate} (≤ 100%, 符合预期)')
else:
    print(f'  ❌ 整体异常率: {rate} (> 100%, 错误!)')
    all_passed = False

# 检查各事项异常率
for item in stats['item_exception_ranking']:
    ir = item['exception_rate']
    if 0 <= ir <= 1.0:
        print(f'  ✅ 事项[{item["item_name"]}]异常率: {ir} (≤ 100%)')
    else:
        print(f'  ❌ 事项[{item["item_name"]}]异常率: {ir} (> 100%, 错误!)')
        all_passed = False

# 检查超时率
tr = stats['timeout_rate']
if 0 <= tr <= 1.0:
    print(f'  ✅ 超时率: {tr} (≤ 100%)')
else:
    print(f'  ❌ 超时率: {tr} (> 100%, 错误!)')
    all_passed = False

# 检查陪同关联异常率
ar = stats['accompany_exception_rate']
if 0 <= ar <= 1.0:
    print(f'  ✅ 陪同关联异常率: {ar} (≤ 100%)')
else:
    print(f'  ❌ 陪同关联异常率: {ar} (> 100%, 错误!)')
    all_passed = False

# 独立统计接口验证
resp = client.get('/api/stats/exceptions/rate')
rate_data = resp.json()['data']
if 0 <= rate_data['exception_rate'] <= 1.0:
    print(f'  ✅ 独立接口异常率: {rate_data["exception_rate"]}')
else:
    print(f'  ❌ 独立接口异常率: {rate_data["exception_rate"]}')
    all_passed = False

resp = client.get('/api/stats/exceptions/accompany-rate')
acc_data = resp.json()['data']
if 0 <= acc_data['accompany_exception_rate'] <= 1.0:
    print(f'  ✅ 独立接口陪同异常率: {acc_data["accompany_exception_rate"]}')
else:
    print(f'  ❌ 独立接口陪同异常率: {acc_data["accompany_exception_rate"]}')
    all_passed = False

# ============================================
# 最终结论
# ============================================
print('\n' + '=' * 60)
if all_passed:
    print('✅ 所有 BUG 修复验证通过!')
else:
    print('❌ 存在 BUG 未修复，请检查上面的错误!')
print('=' * 60)

sys.exit(0 if all_passed else 1)
