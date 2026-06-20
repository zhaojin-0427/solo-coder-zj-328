from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.schemas import UniformResponse, CodeEnum, ServiceItemCreate
from app.database import Database
from app.rules import RuleEngine, DEFAULT_SERVICE_ITEMS

from app.routers import items as items_router
from app.routers import verify as verify_router
from app.routers import history as history_router
from app.routers import stats as stats_router
from app.routers import pre_review as pre_review_router
from app.routers import accompany as accompany_router
from app.routers import exception as exception_router


def uniform_error(code: int, message: str) -> UniformResponse:
    return UniformResponse(code=code, message=message, data=None)


app = FastAPI(
    title="长者办事材料校验、窗口预审与异常闭环处置 API 服务",
    description=(
        "为老人办理医保报销、社保认证、银行卡挂失、住院登记等事项提供材料校验、"
        "缺件提示、代办关系判断、历史查询、窗口预审工单生成、一次性告知、"
        "补齐复核、陪同资源匹配预约、办事过程异常上报与闭环处置和统计分析服务。"
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


db = Database()
db.seed_default_items(DEFAULT_SERVICE_ITEMS)

_items_map = {}
for si in db.list_items(enabled_only=False):
    _items_map[si.item_code] = ServiceItemCreate(
        item_code=si.item_code,
        item_name=si.item_name,
        description=si.description,
        base_materials=si.base_materials,
        agent_required_materials=si.agent_required_materials,
        special_notes=si.special_notes,
        enabled=si.enabled
    )
engine = RuleEngine(_items_map)


def refresh_engine():
    global engine
    items_map = {}
    for si in db.list_items(enabled_only=False):
        items_map[si.item_code] = ServiceItemCreate(
            item_code=si.item_code,
            item_name=si.item_name,
            description=si.description,
            base_materials=si.base_materials,
            agent_required_materials=si.agent_required_materials,
            special_notes=si.special_notes,
            enabled=si.enabled
        )
    engine = RuleEngine(items_map)


items_router.set_db(db)
verify_router.set_db_and_engine(db, engine)
history_router.set_db(db)
stats_router.set_db(db)
pre_review_router.set_db_and_engine(db, engine)
accompany_router.set_db(db)
exception_router.set_db(db)


@app.middleware("http")
async def refresh_engine_on_items_change(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    method = request.method
    if path.startswith("/api/items") and method in ("POST", "PUT", "DELETE"):
        if response.status_code < 400:
            refresh_engine()
            verify_router.set_db_and_engine(db, engine)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg_parts = []
    for e in errors:
        loc = " -> ".join([str(x) for x in e.get("loc", [])])
        msg_parts.append(f"{loc}: {e.get('msg', '')}")
    message = "参数校验失败: " + "; ".join(msg_parts)
    return JSONResponse(
        status_code=422,
        content=uniform_error(CodeEnum.PARAM_ERROR, message).model_dump()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code_map = {
        400: CodeEnum.PARAM_ERROR,
        401: CodeEnum.FAIL,
        403: CodeEnum.FAIL,
        404: CodeEnum.NOT_FOUND,
        500: CodeEnum.SERVER_ERROR,
    }
    code = code_map.get(exc.status_code, CodeEnum.FAIL)
    return JSONResponse(
        status_code=exc.status_code,
        content=uniform_error(code, exc.detail).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=uniform_error(CodeEnum.SERVER_ERROR, f"服务器内部错误: {str(exc)}").model_dump()
    )


@app.get("/", response_model=UniformResponse, summary="服务健康检查")
async def root():
    return uniform_error(CodeEnum.SUCCESS, "长者办事材料校验服务运行中，端口 9505")


@app.get("/health", response_model=UniformResponse, summary="健康检查")
async def health():
    return UniformResponse(
        code=CodeEnum.SUCCESS,
        message="ok",
        data={
            "status": "healthy",
            "service": "elder_material_verify",
            "version": "1.0.0"
        }
    )


app.include_router(items_router.router)
app.include_router(verify_router.router)
app.include_router(history_router.router)
app.include_router(stats_router.router)
app.include_router(pre_review_router.router)
app.include_router(accompany_router.router)
app.include_router(exception_router.router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9505,
        reload=False,
        workers=1
    )
