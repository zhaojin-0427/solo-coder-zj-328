import sys
import os
if os.path.exists('elder_service.db'):
    os.remove('elder_service.db')

sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_all():
    print('=== Step 1: 材料校验 ===')
    resp = client.post('/api/verify', json={
        'item_code': 'MEDICAL_REIMBURSEMENT',
        'elder_type': 'local_resident',
        'is_agent': False,
        'submitted_materials': []
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    verify_data = resp.json()['data']
    verify_id = verify_data.get('verification_id')
    print(f'校验记录ID: {verify_id}')
    assert verify_id is not None

    print()
    print('=== Step 2: 创建预审工单 ===')
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
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    pr_data = resp.json()['data']
    pr_order_id = pr_data['work_order'].get('id')
    print(f'预审工单ID: {pr_order_id}')
    assert pr_order_id is not None

    print()
    print('=== Step 3: 创建陪同人 + 陪同预约 ===')
    resp = client.post('/api/accompany/companions', json={
        'name': '李社工',
        'companion_type': 'social_worker',
        'community': '阳光社区',
        'phone': '13900139000',
        'available_windows': ['medical_window'],
        'eligible_items': ['MEDICAL_REIMBURSEMENT'],
        'skills': ['手语翻译', '轮椅协助']
    })
    print(f'陪同人创建 Status: {resp.status_code}')
    assert resp.status_code == 200

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
    print(f'陪同预约 Status: {resp.status_code}')
    assert resp.status_code == 200
    acc_data = resp.json()['data']['appointment']
    acc_appointment_id = acc_data.get('id')
    print(f'陪同预约ID: {acc_appointment_id}')
    assert acc_appointment_id is not None

    print()
    print('=== Step 4: 上报异常 - 窗口退回 ===')
    resp = client.post('/api/exceptions', json={
        'exception_type': 'window_reject',
        'source_type': 'verify_record',
        'source_id': verify_id,
        'reporter': '窗口工作人员A',
        'reporter_role': '窗口工作人员',
        'reporter_phone': '13600136000',
        'description': '老人提交的医疗发票复印件模糊不清，窗口要求提供原件',
        'location': '医保窗口1号',
        'impact_completion': True,
        'evidence_images': []
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    exc1_data = resp.json()['data']
    exc1_id = exc1_data.get('id')
    print(f'异常1 ID: {exc1_id}')
    print(f'异常单号: {exc1_data.get("exception_no")}')
    print(f'优先级: {exc1_data.get("priority")}')
    print(f'责任角色: {exc1_data.get("responsible_role")}')
    print(f'建议处理动作数量: {len(exc1_data.get("suggested_actions", []))}')
    assert exc1_id is not None
    assert exc1_data.get('exception_no', '').startswith('EX')
    assert len(exc1_data.get('suggested_actions', [])) > 0

    print()
    print('=== Step 5: 上报异常 - 材料被判无效 ===')
    resp = client.post('/api/exceptions', json={
        'exception_type': 'material_invalid',
        'source_type': 'pre_review_order',
        'source_id': pr_order_id,
        'reporter': '预审员B',
        'reporter_role': '预审员',
        'description': '身份证已过有效期，需提供新证件',
        'impact_completion': True
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    exc2_data = resp.json()['data']
    exc2_id = exc2_data.get('id')
    print(f'异常2 ID: {exc2_id}')
    print(f'老人姓名: {exc2_data.get("elder_name")}')
    print(f'事项名称: {exc2_data.get("item_name")}')
    assert exc2_data.get('elder_name') == '张三'
    assert exc2_data.get('item_name') is not None

    print()
    print('=== Step 6: 上报异常 - 老人身体不适 ===')
    resp = client.post('/api/exceptions', json={
        'exception_type': 'elder_unwell',
        'source_type': 'accompany_appointment',
        'source_id': acc_appointment_id,
        'reporter': '陪同人李社工',
        'reporter_role': '陪同人',
        'description': '老人出门前突然头晕，无法前往办事大厅',
        'community': '阳光社区',
        'impact_completion': True
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    exc3_data = resp.json()['data']
    exc3_id = exc3_data.get('id')
    print(f'异常3 ID: {exc3_id}')
    print(f'优先级: {exc3_data.get("priority")}')
    print(f'社区: {exc3_data.get("community")}')
    assert exc3_data.get('priority') == 'p1_urgent'
    assert exc3_data.get('community') == '阳光社区'

    print()
    print('=== Step 7: 获取异常详情 ===')
    resp = client.get(f'/api/exceptions/{exc1_id}')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    detail = resp.json()['data']
    print(f'处理记录数: {len(detail["processing_records"])}')
    print(f'状态历史数: {len(detail["status_history"])}')
    print(f'关联来源信息存在: {detail["source_info"] is not None}')
    assert len(detail['status_history']) > 0
    assert detail['source_info'] is not None

    print()
    print('=== Step 8: 指派责任人 ===')
    resp = client.post(f'/api/exceptions/{exc1_id}/assign', json={
        'responsible_role': 'window_staff',
        'responsible_person': '王主管',
        'responsible_phone': '13700137000',
        'assigned_by': '系统管理员',
        'assign_remark': '请尽快联系家属解决材料问题'
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    assigned = resp.json()['data']
    print(f'责任人: {assigned.get("responsible_person")}')
    print(f'状态: {assigned.get("status")}')
    assert assigned.get('responsible_person') == '王主管'
    assert assigned.get('status') == 'assigned'

    print()
    print('=== Step 9: 追加处理记录 ===')
    resp = client.post(f'/api/exceptions/{exc1_id}/records', json={
        'exception_id': exc1_id,
        'processor': '王主管',
        'action': '电话联系家属',
        'result': '已联系张小明，告知需要提供医疗发票原件，约定明天重新提交',
        'next_step': '明天等待家属提交新的材料后进行复核',
        'duration_minutes': 15
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    record = resp.json()['data']
    print(f'处理记录ID: {record.get("id")}')
    assert record.get('processor') == '王主管'

    print()
    print('=== Step 10: 更新状态为已解决 ===')
    resp = client.put(f'/api/exceptions/{exc1_id}/status', json={
        'status': 'resolved',
        'operator': '王主管',
        'remark': '家属已提交清晰的医疗发票原件'
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    updated = resp.json()['data']
    print(f'状态: {updated.get("status")}')
    assert updated.get('status') == 'resolved'

    print()
    print('=== Step 11: 关闭确认 ===')
    resp = client.post(f'/api/exceptions/{exc1_id}/close', json={
        'closed_by': '系统管理员',
        'close_remark': '问题已解决，老人成功办理医保报销',
        'is_resolved': True,
        'follow_up_suggestion': '3天后回访老人，确认报销是否到账'
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    closed = resp.json()['data']
    print(f'关闭状态: {closed.get("status")}')
    print(f'关闭人: {closed.get("closed_by")}')
    assert closed.get('status') == 'closed'
    assert closed.get('closed_by') == '系统管理员'

    print()
    print('=== Step 12: 异常列表筛选 - 按异常类型 ===')
    resp = client.get('/api/exceptions/list', params={
        'exception_type': 'window_reject',
        'page': 1,
        'page_size': 10
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    list_data = resp.json()['data']
    print(f'总数: {list_data["total"]}')
    print(f'本页数量: {len(list_data["items"])}')
    assert list_data['total'] >= 1

    print()
    print('=== Step 13: 异常列表筛选 - 按责任人 ===')
    resp = client.get('/api/exceptions/list', params={
        'responsible_person': '王主管',
        'page': 1,
        'page_size': 10
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    list_data = resp.json()['data']
    print(f'王主管负责的异常数: {list_data["total"]}')
    assert list_data['total'] >= 1

    print()
    print('=== Step 14: 异常列表筛选 - 按社区 ===')
    resp = client.get('/api/exceptions/list', params={
        'community': '阳光社区',
        'page': 1,
        'page_size': 10
    })
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    list_data = resp.json()['data']
    print(f'阳光社区异常数: {list_data["total"]}')
    assert list_data['total'] >= 1

    print()
    print('=== Step 15: 异常综合统计 ===')
    resp = client.get('/api/stats/exceptions/overall')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    stats = resp.json()['data']
    print(f'异常总数: {stats["total_exceptions"]}')
    print(f'异常发生率: {stats["exception_rate"]}')
    print(f'待处理: {stats["pending_count"]}')
    print(f'处理中: {stats["in_progress_count"]}')
    print(f'已关闭: {stats["closed_count"]}')
    print(f'超时数: {stats["timeout_count"]}')
    print(f'各事项异常排行数: {len(stats["item_exception_ranking"])}')
    print(f'陪同关联异常率: {stats["accompany_exception_rate"]}')
    assert stats['total_exceptions'] >= 3
    assert stats['closed_count'] >= 1

    print()
    print('=== Step 16: 高频失败原因排行 ===')
    resp = client.get('/api/stats/exceptions/top-failure-reasons')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    reasons = resp.json()['data']
    print(f'影响办事的异常总数: {reasons["total_impacted_failures"]}')
    for r in reasons['top_reasons'][:3]:
        print(f'  {r["rank"]}. {r["reason"]}: {r["count"]}次')
    assert reasons['total_impacted_failures'] >= 3

    print()
    print('=== Step 17: 不同异常类型平均处理时长 ===')
    resp = client.get('/api/stats/exceptions/avg-duration')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    durations = resp.json()['data']
    for d in durations['type_avg_duration']:
        print(f'  {d["exception_type_name"]}: {d["avg_duration_minutes"]}分钟 ({d["count"]}个)')
    assert len(durations['type_avg_duration']) >= 3

    print()
    print('=== Step 18: 超时统计 ===')
    resp = client.get('/api/stats/exceptions/timeout-summary')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    timeout = resp.json()['data']
    print(timeout['interpretation'])
    assert 'interpretation' in timeout

    print()
    print('=== Step 19: 陪同关联异常率 ===')
    resp = client.get('/api/stats/exceptions/accompany-rate')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    acc_rate = resp.json()['data']
    print(f'陪同预约总数: {acc_rate["accompany_total"]}')
    print(f'陪同关联异常数: {acc_rate["accompany_exception_count"]}')
    print(acc_rate['interpretation'])
    assert acc_rate['accompany_total'] >= 1
    assert acc_rate['accompany_exception_count'] >= 1

    print()
    print('=== Step 20: 异常发生率统计 ===')
    resp = client.get('/api/stats/exceptions/rate')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    rate = resp.json()['data']
    print(f'异常发生率: {rate["exception_rate_percent"]}')
    print(rate['interpretation'])
    assert 'exception_rate_percent' in rate

    print()
    print('=== Step 21: 各事项异常排行 ===')
    resp = client.get('/api/stats/exceptions/item-ranking')
    print(f'Status: {resp.status_code}')
    assert resp.status_code == 200
    ranking = resp.json()['data']
    print(f'排行项目数: {ranking["total_exception_items"]}')
    assert ranking['total_exception_items'] >= 1

    print()
    print('=== 所有测试通过！ ===')


if __name__ == '__main__':
    test_all()
