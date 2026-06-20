from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum


class CodeEnum(int, Enum):
    SUCCESS = 0
    FAIL = 1
    PARAM_ERROR = 400
    NOT_FOUND = 404
    SERVER_ERROR = 500


class ElderType(str, Enum):
    LOCAL_RESIDENT = "local_resident"
    REMOTE_RESIDENT = "remote_resident"
    SPECIAL_ELDER = "special_elder"
    DISABLED = "disabled"
    LOW_INCOME = "low_income"


class AgentRelation(str, Enum):
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    OTHER_RELATIVE = "other_relative"
    GUARDIAN = "guardian"
    COMMUNITY_STAFF = "community_staff"
    OTHER = "other"


class MaterialCategory(str, Enum):
    ID_CARD = "id_card"
    MEDICAL_CARD = "medical_card"
    SOCIAL_CARD = "social_card"
    BANK_CARD = "bank_card"
    HOUSEHOLD_REGISTER = "household_register"
    AUTHORIZATION_LETTER = "authorization_letter"
    PHOTO = "photo"
    COPY = "copy"
    MEDICAL_RECORD = "medical_record"
    HOSPITAL_CERT = "hospital_cert"
    INCOME_PROOF = "income_proof"
    DISABILITY_CERT = "disability_cert"
    OTHER = "other"


class PhotoSpec(str, Enum):
    ONE_INCH = "1inch"
    TWO_INCH = "2inch"
    WHITE_BG = "white_bg"
    COLORED = "colored"
    DIGITAL = "digital"


class PreReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    SUPPLEMENTING = "supplementing"
    PASSED = "passed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ServiceWindow(str, Enum):
    MEDICAL_WINDOW = "medical_window"
    SOCIAL_SECURITY_WINDOW = "social_security_window"
    BANKING_WINDOW = "banking_window"
    CIVIL_AFFAIRS_WINDOW = "civil_affairs_window"
    COMPREHENSIVE_WINDOW = "comprehensive_window"
    REGISTRATION_WINDOW = "registration_window"


class UniformResponse(BaseModel):
    code: int = Field(default=0, description="响应码，0成功，非0失败")
    message: str = Field(default="success", description="响应消息")
    data: Optional[Any] = Field(default=None, description="响应数据")


class MaterialSpec(BaseModel):
    name: str
    category: MaterialCategory
    required: bool = True
    need_original: bool = True
    need_copy: int = 0
    need_photo_spec: Optional[PhotoSpec] = None
    description: str = ""


class SpecialNote(BaseModel):
    elder_type: ElderType
    note: str
    extra_materials: List[MaterialSpec] = []


class ServiceItemCreate(BaseModel):
    item_code: str
    item_name: str
    description: str = ""
    base_materials: List[MaterialSpec] = []
    agent_required_materials: List[MaterialSpec] = []
    special_notes: List[SpecialNote] = []
    enabled: bool = True


class ServiceItemUpdate(BaseModel):
    item_name: Optional[str] = None
    description: Optional[str] = None
    base_materials: Optional[List[MaterialSpec]] = None
    agent_required_materials: Optional[List[MaterialSpec]] = None
    special_notes: Optional[List[SpecialNote]] = None
    enabled: Optional[bool] = None


class ServiceItem(BaseModel):
    id: int
    item_code: str
    item_name: str
    description: str
    base_materials: List[MaterialSpec]
    agent_required_materials: List[MaterialSpec]
    special_notes: List[SpecialNote]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SubmittedMaterial(BaseModel):
    category: MaterialCategory
    name: str
    has_original: bool = False
    copy_count: int = 0
    photo_spec: Optional[PhotoSpec] = None
    remarks: str = ""


class VerifyRequest(BaseModel):
    item_code: str
    elder_type: ElderType
    is_agent: bool = False
    agent_relation: Optional[AgentRelation] = None
    submitted_materials: List[SubmittedMaterial] = []


class MissingDetail(BaseModel):
    category: MaterialCategory
    name: str
    missing_type: str
    required_count: int = 0
    actual_count: int = 0
    required_spec: Optional[str] = None
    actual_spec: Optional[str] = None
    suggestion: str


class VerifyResult(BaseModel):
    item_code: str
    item_name: str
    is_pass: bool
    missing_list: List[MissingDetail] = []
    supplement_notes: List[str] = []
    special_notices: List[str] = []
    total_required: int = 0
    total_missing: int = 0
    verification_id: Optional[int] = None


class HistoryRecord(BaseModel):
    id: int
    item_code: str
    item_name: str
    elder_type: str
    is_agent: bool
    agent_relation: Optional[str]
    is_pass: bool
    missing_count: int
    missing_categories: str
    created_at: datetime
    make_up_count: int = 0


class StatsItemMissRate(BaseModel):
    item_code: str
    item_name: str
    total_queries: int
    pass_count: int
    miss_count: int
    miss_rate: float


class StatsTopErrorMaterial(BaseModel):
    category: str
    name: str
    miss_count: int
    miss_rate: float
    rank: int


class StatsAgentDistribution(BaseModel):
    agent_relation: str
    count: int
    ratio: float
    avg_miss_count: float


class StatsOverall(BaseModel):
    total_queries: int
    overall_miss_rate: float
    avg_make_up_count: float
    top_items: List[StatsItemMissRate] = []
    top_materials: List[StatsTopErrorMaterial] = []
    agent_distribution: List[StatsAgentDistribution] = []


class PreReviewSubmitRequest(BaseModel):
    item_code: str
    elder_type: ElderType
    elder_id_card: str = Field(..., min_length=8, max_length=20, description="老人身份证号/身份标识")
    elder_name: str = Field(..., min_length=1, max_length=50, description="老人姓名")
    is_agent: bool = False
    agent_relation: Optional[AgentRelation] = None
    agent_name: Optional[str] = None
    contact_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="联系电话")
    submitted_materials: List[SubmittedMaterial] = []
    expected_window: Optional[ServiceWindow] = None
    appointment_date: Optional[str] = Field(None, description="预约办理日期 YYYY-MM-DD")
    remarks: Optional[str] = None


class MaterialCheckSummaryItem(BaseModel):
    category: str
    name: str
    required: bool
    status: str
    note: str
    has_original: bool
    copy_count: int
    required_copy_count: int


class PrintableCheckSummary(BaseModel):
    work_order_no: str
    elder_name: str
    item_name: str
    appointment_date: Optional[str]
    expected_window: Optional[str]
    risk_level: str
    total_required: int
    total_ready: int
    total_missing: int
    materials: List[MaterialCheckSummaryItem]
    deadline: str
    contact_phone: str
    generated_at: str


class PreReviewWorkOrder(BaseModel):
    id: int
    work_order_no: str
    item_code: str
    item_name: str
    elder_type: str
    elder_id_card: str
    elder_name: str
    is_agent: bool
    agent_relation: Optional[str]
    agent_name: Optional[str]
    contact_phone: str
    expected_window: Optional[str]
    appointment_date: Optional[str]
    remarks: Optional[str]
    status: str
    risk_level: str
    is_pass: bool
    total_required: int
    total_missing: int
    total_ready: int
    one_time_notice: str
    suggestion_deadline: datetime
    window_notes: List[str]
    missing_list_json: str
    ready_materials_json: str
    check_summary_json: str
    is_duplicate: bool
    linked_original_id: Optional[int]
    review_count: int
    supplement_count: int
    created_at: datetime
    updated_at: datetime
    reviewer: Optional[str]
    reviewed_at: Optional[datetime]


class PreReviewWorkOrderDetail(BaseModel):
    order: PreReviewWorkOrder
    missing_list: List[Dict[str, Any]]
    ready_materials: List[Dict[str, Any]]
    check_summary: PrintableCheckSummary
    linked_orders: List[Dict[str, Any]]
    supplement_progress: Dict[str, Any]
    repeated_missing_reasons: List[Dict[str, Any]]
    notice_records: List[Dict[str, Any]]


class PreReviewListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PreReviewWorkOrder]


class PreReviewStatusUpdateRequest(BaseModel):
    status: PreReviewStatus
    reviewer: Optional[str] = None
    review_remark: Optional[str] = None


class SupplementReviewRequest(BaseModel):
    work_order_id: int
    reviewer: str = Field(..., description="复核人")
    supplemented_materials: List[SubmittedMaterial] = []
    review_result: bool = Field(..., description="复核结果: True-补齐通过, False-仍有缺件")
    review_remark: Optional[str] = None


class OneTimeNoticeRecord(BaseModel):
    id: int
    work_order_id: int
    work_order_no: str
    notice_type: str
    notice_content: str
    notice_method: str
    notified_to: str
    notified_phone: str
    created_at: datetime


class PreReviewStats(BaseModel):
    total_orders: int
    pass_count: int
    pass_rate: float
    duplicate_count: int
    duplicate_rate: float
    avg_missing_count: float
    expired_count: int
    supplement_in_progress_count: int
    item_avg_missing: List[Dict[str, Any]]
    top_return_material_combos: List[Dict[str, Any]]
    window_pass_rates: List[Dict[str, Any]]


class PreReviewNoticeQuery(BaseModel):
    work_order_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notice_method: Optional[str] = None
    limit: int = 50
    offset: int = 0


class MobilityLevel(str, Enum):
    NORMAL = "normal"
    NEED_ASSIST = "need_assist"
    WHEELCHAIR = "wheelchair"
    BEDRIDDEN = "bedridden"


class AccompanyDemandType(str, Enum):
    FULL_ACCOMPANY = "full_accompany"
    MATERIAL_ASSIST = "material_assist"
    TRANSPORTATION = "transportation"
    SIGNING_ASSIST = "signing_assist"
    EMOTIONAL_SUPPORT = "emotional_support"


class CompanionType(str, Enum):
    VOLUNTEER = "volunteer"
    SOCIAL_WORKER = "social_worker"
    FAMILY = "family"


class AppointmentStatus(str, Enum):
    PENDING_MATCH = "pending_match"
    MATCHED = "matched"
    CONFIRMED = "confirmed"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    REASSIGNED = "reassigned"


class ConfirmStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    COMPANION_CONFIRMED = "companion_confirmed"
    ELDER_CONFIRMED = "elder_confirmed"
    BOTH_CONFIRMED = "both_confirmed"
    DECLINED = "declined"


class CompanionResourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="陪同人姓名")
    companion_type: CompanionType
    community: str = Field(..., min_length=1, max_length=100, description="所属社区")
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="联系电话")
    id_card: Optional[str] = Field(None, min_length=8, max_length=20, description="身份证号")
    available_windows: List[ServiceWindow] = []
    eligible_items: List[str] = []
    max_daily_count: int = Field(3, ge=1, le=10, description="每日最大陪同次数")
    skills: List[str] = []
    is_active: bool = True
    remarks: Optional[str] = None


class CompanionResourceUpdate(BaseModel):
    name: Optional[str] = None
    companion_type: Optional[CompanionType] = None
    community: Optional[str] = None
    phone: Optional[str] = None
    id_card: Optional[str] = None
    available_windows: Optional[List[ServiceWindow]] = None
    eligible_items: Optional[List[str]] = None
    max_daily_count: Optional[int] = None
    skills: Optional[List[str]] = None
    is_active: Optional[bool] = None
    remarks: Optional[str] = None


class CompanionResource(BaseModel):
    id: int
    name: str
    companion_type: str
    community: str
    phone: str
    id_card: Optional[str]
    available_windows: List[str]
    eligible_items: List[str]
    max_daily_count: int
    skills: List[str]
    is_active: bool
    remarks: Optional[str]
    created_at: datetime
    updated_at: datetime


class AccompanyAppointmentCreate(BaseModel):
    elder_name: str = Field(..., min_length=1, max_length=50, description="老人姓名")
    elder_type: ElderType
    item_code: str = Field(..., description="办理事项编码")
    mobility_level: MobilityLevel
    is_living_alone: bool = Field(False, description="是否独居")
    accompany_demand_type: AccompanyDemandType
    expected_date: str = Field(..., description="期望办理日期 YYYY-MM-DD")
    community: str = Field(..., min_length=1, max_length=100, description="所在社区")
    contact_phone: str = Field(..., pattern=r"^1[3-9]\d{9}$", description="联系电话")
    special_notes: Optional[str] = Field(None, description="特殊备注")
    pre_review_order_id: Optional[int] = Field(None, description="关联预审工单ID")
    verify_history_id: Optional[int] = Field(None, description="关联校验记录ID")
    expected_window: Optional[ServiceWindow] = None


class MatchedCompanion(BaseModel):
    companion_id: int
    companion_name: str
    companion_type: str
    phone: str
    community: str
    match_priority: int
    match_score: float
    match_reasons: List[str]


class AccompanyAppointment(BaseModel):
    id: int
    appointment_no: str
    elder_name: str
    elder_type: str
    item_code: str
    item_name: str
    mobility_level: str
    is_living_alone: bool
    accompany_demand_type: str
    expected_date: str
    community: str
    contact_phone: str
    special_notes: Optional[str]
    pre_review_order_id: Optional[int]
    verify_history_id: Optional[int]
    expected_window: Optional[str]
    status: str
    risk_level: str
    missing_materials: List[Dict[str, Any]]
    match_priority: int
    recommended_companion_id: Optional[int]
    recommended_companion_name: Optional[str]
    recommended_companion_type: Optional[str]
    recommended_companion_phone: Optional[str]
    expected_service_period: Optional[str]
    material_reminders: List[str]
    route_hints: List[str]
    risk_alerts: List[str]
    confirm_status: str
    cancel_reason: Optional[str]
    cancel_remark: Optional[str]
    created_at: datetime
    updated_at: datetime


class AccompanyAppointmentDetail(BaseModel):
    appointment: AccompanyAppointment
    matched_candidates: List[MatchedCompanion]
    related_pre_review_order: Optional[Dict[str, Any]]
    service_history: List[Dict[str, Any]]


class AccompanyAppointmentReassign(BaseModel):
    new_companion_id: int = Field(..., description="新陪同人ID")
    reassign_reason: str = Field(..., min_length=1, description="改派原因")
    operator: str = Field(..., min_length=1, description="操作人")


class AccompanyStatusUpdate(BaseModel):
    status: AppointmentStatus
    operator: Optional[str] = None
    remark: Optional[str] = None


class AccompanyCancelRequest(BaseModel):
    cancel_reason: str = Field(..., min_length=1, description="取消原因分类")
    cancel_remark: Optional[str] = Field(None, description="取消详细说明")
    operator: Optional[str] = None


class AccompanyFollowUpCreate(BaseModel):
    appointment_id: int
    is_companion_arrived: bool = Field(..., description="陪同人是否按时到达")
    is_elder_satisfied: bool = Field(..., description="老人是否满意")
    materials_completed: bool = Field(..., description="材料是否齐全")
    failed_materials: List[str] = []
    service_duration_minutes: int = Field(0, ge=0, description="服务时长(分钟)")
    issues: List[str] = []
    suggestions: Optional[str] = None
    follower: str = Field(..., min_length=1, description="回访人")


class AccompanyFollowUpRecord(BaseModel):
    id: int
    appointment_id: int
    appointment_no: str
    is_companion_arrived: bool
    is_elder_satisfied: bool
    materials_completed: bool
    failed_materials: List[str]
    service_duration_minutes: int
    issues: List[str]
    suggestions: Optional[str]
    follower: str
    created_at: datetime


class AccompanyStatsCommunity(BaseModel):
    community: str
    total_appointments: int
    completed_count: int
    completion_rate: float
    no_show_count: int
    no_show_rate: float


class AccompanyStatsRiskCoverage(BaseModel):
    community: str
    high_risk_elder_count: int
    accompanied_count: int
    coverage_rate: float


class AccompanyStatsCompanionWorkload(BaseModel):
    companion_id: int
    companion_name: str
    companion_type: str
    community: str
    total_services: int
    avg_duration_minutes: float


class AccompanyStatsMaterialFailure(BaseModel):
    material_name: str
    failure_count: int
    rank: int


class AccompanyStatsOverall(BaseModel):
    total_appointments: int
    completed_count: int
    completion_rate: float
    no_show_count: int
    no_show_rate: float
    cancelled_count: int
    avg_service_duration_minutes: float
    satisfaction_rate: float
    community_stats: List[AccompanyStatsCommunity]
    risk_coverage_stats: List[AccompanyStatsRiskCoverage]
    companion_workload_ranking: List[AccompanyStatsCompanionWorkload]
    material_failure_ranking: List[AccompanyStatsMaterialFailure]


class ExceptionType(str, Enum):
    WINDOW_REJECT = "window_reject"
    MATERIAL_INVALID = "material_invalid"
    ELDER_ABSENT = "elder_absent"
    COMPANION_LATE = "companion_late"
    SUPPLEMENT_FAIL = "supplement_fail"
    POLICY_CHANGED = "policy_changed"
    ELDER_UNWELL = "elder_unwell"
    OTHER = "other"


class ExceptionStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DisposalPriority(str, Enum):
    P1_URGENT = "p1_urgent"
    P2_HIGH = "p2_high"
    P3_MEDIUM = "p3_medium"
    P4_LOW = "p4_low"


class ResponsibleRole(str, Enum):
    WINDOW_STAFF = "window_staff"
    COMMUNITY_WORKER = "community_worker"
    ACCOMPANY_MANAGER = "accompany_manager"
    SUPERVISOR = "supervisor"
    MEDICAL_STAFF = "medical_staff"


class ExceptionCreateRequest(BaseModel):
    source_type: str
    source_id: int
    exception_type: str
    reporter: str
    reporter_role: str
    reporter_phone: Optional[str] = None
    description: str
    location: Optional[str] = None
    impact_completion: bool = True
    evidence_images: Optional[List[str]] = None
    extra_info: Optional[Dict[str, Any]] = None


class ExceptionStatusUpdateRequest(BaseModel):
    status: str
    operator: str
    remark: Optional[str] = None


class ExceptionAssignRequest(BaseModel):
    responsible_role: Optional[str] = None
    responsible_person: str
    responsible_phone: Optional[str] = None
    assigned_by: str
    assign_remark: Optional[str] = None


class ExceptionProcessingRecordCreate(BaseModel):
    processor: str
    action: str
    result: str
    next_step: Optional[str] = None
    duration_minutes: int = 0


class ExceptionCloseRequest(BaseModel):
    closed_by: str
    close_remark: str
    is_resolved: bool = True
    follow_up_suggestion: Optional[str] = None


class ExceptionDisposalOrder(BaseModel):
    id: int
    exception_no: str
    exception_type: str
    source_type: str
    source_id: int
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    elder_name: Optional[str] = None
    elder_type: Optional[str] = None
    community: Optional[str] = None
    expected_window: Optional[str] = None
    reporter: str
    reporter_role: str
    reporter_phone: Optional[str] = None
    description: str
    location: Optional[str] = None
    impact_completion: bool = True
    risk_level: str = "medium"
    status: str = "pending"
    priority: str = "p3_medium"
    responsible_role: str = "supervisor"
    responsible_person: Optional[str] = None
    responsible_phone: Optional[str] = None
    suggested_actions: List[str] = []
    latest_deadline: Optional[datetime] = None
    follow_up_required: bool = True
    follow_up_deadline: Optional[datetime] = None
    evidence_images: Optional[List[str]] = None
    extra_info: Optional[Dict[str, Any]] = None
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None
    close_remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExceptionProcessingRecord(BaseModel):
    id: int
    exception_id: int
    processor: str
    action: str
    result: str
    next_step: Optional[str] = None
    duration_minutes: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExceptionStatusHistory(BaseModel):
    id: int
    exception_id: int
    from_status: Optional[str] = None
    to_status: str
    operator: str
    remark: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExceptionStatsItemRank(BaseModel):
    item_code: str
    item_name: str
    exception_count: int
    exception_rate: float
    rank: int


class ExceptionStatsTypeAvgDuration(BaseModel):
    exception_type: str
    exception_type_name: str
    avg_duration_minutes: float
    count: int


class ExceptionStatsFailureReason(BaseModel):
    reason: str
    count: int
    rank: int


class ExceptionStatsOverall(BaseModel):
    total_exceptions: int
    exception_rate: float
    pending_count: int
    in_progress_count: int
    resolved_count: int
    closed_count: int
    timeout_count: int
    timeout_rate: float
    item_exception_ranking: List[ExceptionStatsItemRank]
    type_avg_duration: List[ExceptionStatsTypeAvgDuration]
    top_failure_reasons: List[ExceptionStatsFailureReason]
    accompany_exception_rate: float
    accompany_exception_count: int
    accompany_total: int


class PolicyChangeStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class PolicyRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WarningStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"


class WarningSourceType(str, Enum):
    VERIFY_RECORD = "verify_record"
    PRE_REVIEW_ORDER = "pre_review_order"
    ACCOMPANY_APPOINTMENT = "accompany_appointment"


class PolicyChangeCreate(BaseModel):
    title: str
    applicable_items: Optional[List[str]] = []
    applicable_windows: Optional[List[str]] = []
    impacted_materials: Optional[List[Dict[str, Any]]] = []
    impacted_elder_types: Optional[List[str]] = []
    effective_date: str
    expiry_date: Optional[str] = None
    policy_source: str = ""
    risk_level: Optional[str] = "medium"
    handling_suggestion: str = ""
    impact_types: Optional[List[str]] = []
    description: str = ""
    added_materials: Optional[List[Dict[str, Any]]] = []
    removed_materials: Optional[List[Dict[str, Any]]] = []
    rejection_reasons: Optional[List[str]] = []


class PolicyChangeUpdate(BaseModel):
    title: Optional[str] = None
    applicable_items: Optional[List[str]] = None
    applicable_windows: Optional[List[str]] = None
    impacted_materials: Optional[List[Dict[str, Any]]] = None
    impacted_elder_types: Optional[List[str]] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    policy_source: Optional[str] = None
    risk_level: Optional[str] = None
    handling_suggestion: Optional[str] = None
    impact_types: Optional[List[str]] = None
    description: Optional[str] = None
    added_materials: Optional[List[Dict[str, Any]]] = None
    removed_materials: Optional[List[Dict[str, Any]]] = None
    rejection_reasons: Optional[List[str]] = None
    status: Optional[str] = None


class PolicyWarningConfirmRequest(BaseModel):
    confirmed_by: str
    confirm_remark: Optional[str] = None


class PolicyChange(BaseModel):
    id: int
    title: str
    applicable_items: List[str] = []
    applicable_windows: List[str] = []
    impacted_materials: List[Dict[str, Any]] = []
    impacted_elder_types: List[str] = []
    effective_date: str
    expiry_date: Optional[str] = None
    policy_source: str = ""
    risk_level: str = "medium"
    handling_suggestion: str = ""
    impact_types: List[str] = []
    description: str = ""
    added_materials: List[Dict[str, Any]] = []
    removed_materials: List[Dict[str, Any]] = []
    rejection_reasons: List[str] = []
    status: str = "draft"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PolicyWarning(BaseModel):
    id: int
    policy_change_id: int
    policy_title: str
    source_type: str
    source_id: int
    source_no: Optional[str] = None
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    elder_name: Optional[str] = None
    elder_type: Optional[str] = None
    community: Optional[str] = None
    expected_window: Optional[str] = None
    appointment_date: Optional[str] = None
    risk_level: str = "medium"
    status: str = "unconfirmed"
    impact_details: List[Dict[str, Any]] = []
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirm_remark: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
