from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
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
