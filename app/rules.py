from typing import List, Dict, Tuple, Optional
from .schemas import (
    MaterialSpec, SpecialNote, ServiceItemCreate, SubmittedMaterial,
    MissingDetail, VerifyResult, ElderType, AgentRelation,
    MaterialCategory, PhotoSpec
)


DEFAULT_SERVICE_ITEMS: List[ServiceItemCreate] = [
    ServiceItemCreate(
        item_code="MEDICAL_REIMBURSEMENT",
        item_name="医保报销",
        description="办理医疗保险费用报销手续",
        base_materials=[
            MaterialSpec(
                name="居民身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=1,
                description="老人本人有效身份证件"
            ),
            MaterialSpec(
                name="医保卡/社保卡",
                category=MaterialCategory.MEDICAL_CARD,
                required=True, need_original=True, need_copy=0,
                description="需在有效期内"
            ),
            MaterialSpec(
                name="医疗费用发票",
                category=MaterialCategory.MEDICAL_RECORD,
                required=True, need_original=True, need_copy=0,
                description="医院开具的正规发票原件"
            ),
            MaterialSpec(
                name="住院/门诊病历",
                category=MaterialCategory.MEDICAL_RECORD,
                required=True, need_original=False, need_copy=1,
                description="含诊断证明、出院小结"
            ),
            MaterialSpec(
                name="费用明细清单",
                category=MaterialCategory.MEDICAL_RECORD,
                required=True, need_original=True, need_copy=0,
                description="医院盖章的费用清单"
            ),
        ],
        agent_required_materials=[
            MaterialSpec(
                name="代办人身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=1,
                description="代办人本人有效身份证件"
            ),
            MaterialSpec(
                name="授权委托书",
                category=MaterialCategory.AUTHORIZATION_LETTER,
                required=True, need_original=True, need_copy=0,
                description="老人签字/按手印的书面委托书"
            ),
            MaterialSpec(
                name="关系证明",
                category=MaterialCategory.HOUSEHOLD_REGISTER,
                required=False, need_original=True, need_copy=0,
                description="户口本或亲属关系证明（直系亲属可免）"
            ),
        ],
        special_notes=[
            SpecialNote(
                elder_type=ElderType.LOW_INCOME,
                note="低保老人可申请医疗救助，需额外提供低保证明",
                extra_materials=[
                    MaterialSpec(
                        name="低保证/低保边缘证",
                        category=MaterialCategory.INCOME_PROOF,
                        required=True, need_original=True, need_copy=1
                    )
                ]
            ),
            SpecialNote(
                elder_type=ElderType.DISABLED,
                note="残疾人可享受残疾人专项医疗补贴",
                extra_materials=[
                    MaterialSpec(
                        name="残疾人证",
                        category=MaterialCategory.DISABILITY_CERT,
                        required=True, need_original=True, need_copy=1
                    )
                ]
            ),
            SpecialNote(
                elder_type=ElderType.REMOTE_RESIDENT,
                note="异地居住老人需提前办理异地就医备案手续",
                extra_materials=[
                    MaterialSpec(
                        name="异地就医备案表",
                        category=MaterialCategory.OTHER,
                        required=True, need_original=True, need_copy=0
                    )
                ]
            ),
        ],
        enabled=True
    ),
    ServiceItemCreate(
        item_code="SOCIAL_SECURITY_VERIFY",
        item_name="社保认证",
        description="离退休人员养老金领取资格认证",
        base_materials=[
            MaterialSpec(
                name="居民身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=0,
                description="人脸识别现场核验"
            ),
            MaterialSpec(
                name="养老金银行卡/存折",
                category=MaterialCategory.BANK_CARD,
                required=True, need_original=True, need_copy=0,
                description="发放养老金的账户凭证"
            ),
            MaterialSpec(
                name="近期免冠照片",
                category=MaterialCategory.PHOTO,
                required=False, need_original=True, need_copy=0,
                need_photo_spec=PhotoSpec.ONE_INCH,
                description="1寸白底彩色照片（现场拍照可免）"
            ),
        ],
        agent_required_materials=[
            MaterialSpec(
                name="代办人身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=0
            ),
            MaterialSpec(
                name="授权委托书",
                category=MaterialCategory.AUTHORIZATION_LETTER,
                required=True, need_original=True, need_copy=0,
                description="社区盖章的委托书"
            ),
            MaterialSpec(
                name="近期生活照",
                category=MaterialCategory.PHOTO,
                required=True, need_original=True, need_copy=0,
                need_photo_spec=PhotoSpec.DIGITAL,
                description="手持当日报纸的电子照片，证明生存状态"
            ),
        ],
        special_notes=[
            SpecialNote(
                elder_type=ElderType.SPECIAL_ELDER,
                note="高龄独居老人可申请社区工作人员上门认证",
                extra_materials=[]
            ),
            SpecialNote(
                elder_type=ElderType.DISABLED,
                note="行动不便的残疾人可预约上门服务",
                extra_materials=[]
            ),
        ],
        enabled=True
    ),
    ServiceItemCreate(
        item_code="BANK_CARD_REPORT_LOSS",
        item_name="银行卡挂失",
        description="办理银行借记卡/存折挂失及补办手续",
        base_materials=[
            MaterialSpec(
                name="居民身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=2,
                description="本人有效身份证原件"
            ),
            MaterialSpec(
                name="挂失银行卡卡号",
                category=MaterialCategory.BANK_CARD,
                required=True, need_original=False, need_copy=0,
                description="若记不清卡号可凭身份证现场查询"
            ),
            MaterialSpec(
                name="挂失申请书",
                category=MaterialCategory.OTHER,
                required=False, need_original=True, need_copy=0,
                description="银行网点现场填写"
            ),
        ],
        agent_required_materials=[
            MaterialSpec(
                name="代办人身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=2
            ),
            MaterialSpec(
                name="公证委托书",
                category=MaterialCategory.AUTHORIZATION_LETTER,
                required=True, need_original=True, need_copy=0,
                description="经公证处公证的授权书（挂失补卡必须本人办理，部分银行允许代办挂失仅止付）"
            ),
            MaterialSpec(
                name="关系证明",
                category=MaterialCategory.HOUSEHOLD_REGISTER,
                required=True, need_original=True, need_copy=1,
                description="户口本或结婚证等直系亲属证明"
            ),
        ],
        special_notes=[
            SpecialNote(
                elder_type=ElderType.SPECIAL_ELDER,
                note="高龄老人可联系银行申请上门核实服务",
                extra_materials=[]
            ),
        ],
        enabled=True
    ),
    ServiceItemCreate(
        item_code="HOSPITAL_REGISTRATION",
        item_name="住院登记",
        description="办理医院入院登记手续",
        base_materials=[
            MaterialSpec(
                name="居民身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=1,
                description="患者本人身份证"
            ),
            MaterialSpec(
                name="医保卡/社保卡",
                category=MaterialCategory.MEDICAL_CARD,
                required=True, need_original=True, need_copy=0,
                description="医保实时结算使用"
            ),
            MaterialSpec(
                name="入院通知书",
                category=MaterialCategory.HOSPITAL_CERT,
                required=True, need_original=True, need_copy=0,
                description="医生开具的住院证"
            ),
            MaterialSpec(
                name="近期免冠照片",
                category=MaterialCategory.PHOTO,
                required=False, need_original=True, need_copy=0,
                need_photo_spec=PhotoSpec.TWO_INCH,
                description="2寸白底彩色照片（办理腕带/陪护证用）"
            ),
            MaterialSpec(
                name="门诊病历资料",
                category=MaterialCategory.MEDICAL_RECORD,
                required=False, need_original=True, need_copy=0,
                description="既往就诊记录、检查报告"
            ),
        ],
        agent_required_materials=[
            MaterialSpec(
                name="办理人身份证",
                category=MaterialCategory.ID_CARD,
                required=True, need_original=True, need_copy=1,
                description="陪同家属或代办人身份证"
            ),
            MaterialSpec(
                name="联系人信息登记",
                category=MaterialCategory.OTHER,
                required=False, need_original=False, need_copy=0,
                description="医院住院处填写紧急联系人表"
            ),
        ],
        special_notes=[
            SpecialNote(
                elder_type=ElderType.LOW_INCOME,
                note="低保困难老人可申请先诊疗后付费，需提供低保证明",
                extra_materials=[
                    MaterialSpec(
                        name="低保证/扶贫手册",
                        category=MaterialCategory.INCOME_PROOF,
                        required=False, need_original=True, need_copy=1
                    )
                ]
            ),
            SpecialNote(
                elder_type=ElderType.DISABLED,
                note="残疾人可享受残疾人病房优先安排",
                extra_materials=[
                    MaterialSpec(
                        name="残疾人证",
                        category=MaterialCategory.DISABILITY_CERT,
                        required=False, need_original=True, need_copy=1
                    )
                ]
            ),
        ],
        enabled=True
    ),
]


AGENT_RELATION_RULES: Dict[AgentRelation, Dict] = {
    AgentRelation.SPOUSE: {
        "label": "配偶",
        "need_authorization": True,
        "need_relation_proof": True,
        "priority_level": "high",
        "relation_proof_desc": "结婚证",
        "confusion_materials": ["结婚证复印件需盖民政局鲜章", "注意区分配偶代办与子女代办的签字权限"]
    },
    AgentRelation.CHILD: {
        "label": "子女",
        "need_authorization": True,
        "need_relation_proof": False,
        "priority_level": "high",
        "relation_proof_desc": "户口本/出生证明（可选）",
        "confusion_materials": ["多个子女代办时只需一人到场，但需提供其他子女同意书（部分银行）"]
    },
    AgentRelation.PARENT: {
        "label": "父母",
        "need_authorization": True,
        "need_relation_proof": True,
        "priority_level": "medium",
        "relation_proof_desc": "户口本",
        "confusion_materials": []
    },
    AgentRelation.OTHER_RELATIVE: {
        "label": "其他亲属",
        "need_authorization": True,
        "need_relation_proof": True,
        "priority_level": "medium",
        "relation_proof_desc": "派出所出具的亲属关系证明",
        "confusion_materials": ["部分银行不接受其他亲属代办挂失补卡，请提前核实"]
    },
    AgentRelation.GUARDIAN: {
        "label": "法定监护人",
        "need_authorization": False,
        "need_relation_proof": True,
        "priority_level": "high",
        "relation_proof_desc": "法院判决书/居委会指定监护人证明",
        "confusion_materials": ["监护人证明需为原件，复印件无效"]
    },
    AgentRelation.COMMUNITY_STAFF: {
        "label": "社区工作人员",
        "need_authorization": True,
        "need_relation_proof": True,
        "priority_level": "low",
        "relation_proof_desc": "社区居委会介绍信+工作证",
        "confusion_materials": ["社区代办需老人签字确认，居委会盖章见证"]
    },
    AgentRelation.OTHER: {
        "label": "其他代办人",
        "need_authorization": True,
        "need_relation_proof": True,
        "priority_level": "low",
        "relation_proof_desc": "公证委托书",
        "confusion_materials": ["多数敏感业务（挂失、取大额现金）不接受非亲属代办", "授权书必须经公证处公证"]
    },
}


PHOTO_SPEC_LABELS: Dict[PhotoSpec, str] = {
    PhotoSpec.ONE_INCH: "1寸（25mm×35mm）",
    PhotoSpec.TWO_INCH: "2寸（35mm×49mm）",
    PhotoSpec.WHITE_BG: "白底背景",
    PhotoSpec.COLORED: "彩色照片",
    PhotoSpec.DIGITAL: "电子照片（JPG格式，≥300dpi）",
}


MATERIAL_LABELS: Dict[MaterialCategory, str] = {
    MaterialCategory.ID_CARD: "身份证件",
    MaterialCategory.MEDICAL_CARD: "医保卡/社保卡",
    MaterialCategory.SOCIAL_CARD: "社保卡",
    MaterialCategory.BANK_CARD: "银行卡/存折",
    MaterialCategory.HOUSEHOLD_REGISTER: "户口本/关系证明",
    MaterialCategory.AUTHORIZATION_LETTER: "授权委托书",
    MaterialCategory.PHOTO: "照片",
    MaterialCategory.COPY: "复印件",
    MaterialCategory.MEDICAL_RECORD: "医疗记录/票据",
    MaterialCategory.HOSPITAL_CERT: "医院证明",
    MaterialCategory.INCOME_PROOF: "收入/低保证明",
    MaterialCategory.DISABILITY_CERT: "残疾人证",
    MaterialCategory.OTHER: "其他材料",
}


class RuleEngine:
    """规则引擎：负责事项规则匹配、材料校验、缺件判断、代办关系判断"""

    def __init__(self, service_items: Dict[str, ServiceItemCreate]):
        self.service_items = service_items

    def get_required_materials(
        self,
        item_code: str,
        elder_type: ElderType,
        is_agent: bool,
        agent_relation: Optional[AgentRelation] = None
    ) -> Tuple[List[MaterialSpec], List[str], List[str]]:
        """根据事项、老人类型、是否代办，汇总所有必选材料"""
        if item_code not in self.service_items:
            raise ValueError(f"未知事项编码: {item_code}")

        item = self.service_items[item_code]
        all_materials: List[MaterialSpec] = list(item.base_materials)
        supplement_notes: List[str] = []
        special_notices: List[str] = []

        if item.description:
            supplement_notes.append(f"【{item.item_name}】{item.description}")

        for note in item.special_notes:
            if note.elder_type == elder_type:
                special_notices.append(note.note)
                if note.extra_materials:
                    all_materials.extend(note.extra_materials)
                    names = "、".join([m.name for m in note.extra_materials])
                    supplement_notes.append(f"【特殊人群附加材料】{MATERIAL_LABELS.get(elder_type, elder_type.value)}老人需额外准备：{names}")

        if is_agent and item.agent_required_materials:
            all_materials.extend(item.agent_required_materials)
            if agent_relation and agent_relation in AGENT_RELATION_RULES:
                rule = AGENT_RELATION_RULES[agent_relation]
                special_notices.append(
                    f"【代办关系校验】代办关系：{rule['label']}，"
                    f"{'必须提供授权书' if rule['need_authorization'] else '法定监护人免授权书'}，"
                    f"{'需要提供关系证明（'+rule['relation_proof_desc']+'）' if rule['need_relation_proof'] else '免关系证明'}"
                )
                if rule.get("confusion_materials"):
                    for cm in rule["confusion_materials"]:
                        supplement_notes.append(f"【易混淆提醒】{cm}")

        return all_materials, supplement_notes, special_notices

    def validate_materials(
        self,
        item_code: str,
        elder_type: ElderType,
        is_agent: bool,
        agent_relation: Optional[AgentRelation],
        submitted: List[SubmittedMaterial]
    ) -> VerifyResult:
        """核心校验方法：对比要求与提交，生成缺件清单"""
        if item_code not in self.service_items:
            raise ValueError(f"未知事项编码: {item_code}")

        item = self.service_items[item_code]
        required_materials, supplement_notes, special_notices = self.get_required_materials(
            item_code, elder_type, is_agent, agent_relation
        )

        submitted_by_category: Dict[MaterialCategory, List[SubmittedMaterial]] = {}
        for sm in submitted:
            if sm.category not in submitted_by_category:
                submitted_by_category[sm.category] = []
            submitted_by_category[sm.category].append(sm)

        missing_list: List[MissingDetail] = []
        total_required = 0

        for req in required_materials:
            if not req.required:
                continue
            total_required += 1

            candidates = submitted_by_category.get(req.category, [])
            matched = None
            for cand in candidates:
                if cand.name == req.name or cand.category == req.category:
                    matched = cand
                    break

            if matched is None:
                missing_list.append(MissingDetail(
                    category=req.category,
                    name=req.name,
                    missing_type="material_missing",
                    required_count=1 if req.need_original else 0,
                    actual_count=0,
                    suggestion=f"缺少{MATERIAL_LABELS[req.category]}：{req.name}{'（原件）' if req.need_original else ''}。{req.description}"
                ))
                if req.need_copy > 0:
                    missing_list.append(MissingDetail(
                        category=MaterialCategory.COPY,
                        name=f"{req.name}复印件",
                        missing_type="copy_missing",
                        required_count=req.need_copy,
                        actual_count=0,
                        suggestion=f"请准备{req.need_copy}份{req.name}的复印件（建议用A4纸，身份证需正反面复印在同一页）"
                    ))
                if req.need_photo_spec:
                    missing_list.append(MissingDetail(
                        category=MaterialCategory.PHOTO,
                        name=req.name,
                        missing_type="photo_spec_missing",
                        required_spec=PHOTO_SPEC_LABELS.get(req.need_photo_spec, req.need_photo_spec.value),
                        suggestion=f"缺少{req.name}，规格要求：{PHOTO_SPEC_LABELS.get(req.need_photo_spec, req.need_photo_spec.value)}"
                    ))
                continue

            if req.need_original and not matched.has_original:
                missing_list.append(MissingDetail(
                    category=req.category,
                    name=req.name,
                    missing_type="original_missing",
                    required_count=1,
                    actual_count=0,
                    suggestion=f"{req.name}缺少原件，请携带原件到现场核验。复印件不可替代原件。"
                ))

            if req.need_copy > 0 and matched.copy_count < req.need_copy:
                missing_list.append(MissingDetail(
                    category=MaterialCategory.COPY,
                    name=f"{req.name}复印件",
                    missing_type="copy_insufficient",
                    required_count=req.need_copy,
                    actual_count=matched.copy_count,
                    suggestion=f"{req.name}复印件数量不足：要求{req.need_copy}份，当前{matched.copy_count}份。请再复印{req.need_copy - matched.copy_count}份。"
                ))

            if req.need_photo_spec and matched.photo_spec != req.need_photo_spec:
                actual_spec_label = PHOTO_SPEC_LABELS.get(matched.photo_spec, "未提交或规格未知") if matched.photo_spec else "未指定"
                required_spec_label = PHOTO_SPEC_LABELS.get(req.need_photo_spec, req.need_photo_spec.value)
                missing_list.append(MissingDetail(
                    category=MaterialCategory.PHOTO,
                    name=req.name,
                    missing_type="photo_spec_mismatch",
                    required_spec=required_spec_label,
                    actual_spec=actual_spec_label,
                    suggestion=f"{req.name}照片规格不符：要求{required_spec_label}，实际{actual_spec_label}。请重新拍摄符合规格的照片。"
                ))

        is_pass = len(missing_list) == 0
        if is_pass:
            supplement_notes.append("所有必选材料已齐全，可前往窗口办理。建议出门前再次核对原件是否带齐。")
        else:
            supplement_notes.append(f"共发现 {len(missing_list)} 项缺件/问题，请对照清单补齐后再前往办理，避免白跑一趟。")
            categories = set([MATERIAL_LABELS[m.category] for m in missing_list])
            supplement_notes.append(f"主要缺少的材料类别：{'、'.join(categories)}")

        return VerifyResult(
            item_code=item_code,
            item_name=item.item_name,
            is_pass=is_pass,
            missing_list=missing_list,
            supplement_notes=supplement_notes,
            special_notices=special_notices,
            total_required=total_required,
            total_missing=len(missing_list),
            verification_id=None
        )

    def check_agent_relation(self, relation: AgentRelation) -> Dict:
        """代办关系判断规则"""
        if relation not in AGENT_RELATION_RULES:
            return {"valid": False, "message": "未知代办关系"}
        rule = AGENT_RELATION_RULES[relation]
        return {
            "valid": True,
            "relation": relation.value,
            "label": rule["label"],
            "need_authorization": rule["need_authorization"],
            "need_relation_proof": rule["need_relation_proof"],
            "relation_proof_desc": rule["relation_proof_desc"],
            "priority_level": rule["priority_level"],
            "confusion_notes": rule.get("confusion_materials", [])
        }
