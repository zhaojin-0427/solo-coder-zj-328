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
