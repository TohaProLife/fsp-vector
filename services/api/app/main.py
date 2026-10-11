import importlib
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from pydantic import ValidationError
from . import auth, models
from .common import Problem
from .config import settings, validate_runtime_configuration
from .db import Base, SessionLocal, engine
from .request_limits import BodyLimitMiddleware
from .readiness import schema_readiness

# Inherit Uvicorn's configured INFO handler instead of the root WARNING level.
logger = logging.getLogger("uvicorn.error.vector.api")


@asynccontextmanager
async def lifespan(app):
    validate_runtime_configuration(settings)
    if not settings.local_demo:
        from .oidc import production_config_errors
        issues = production_config_errors()
        if issues:
            raise RuntimeError("Unsafe identity configuration: " + "; ".join(issues))
    if settings.auto_create_schema:
        Base.metadata.create_all(engine)
    if settings.auto_seed and settings.local_demo:
        try:
            from .seed import seed_database
        except ImportError:
            logger.info("Synthetic fixture module not installed yet")
        else:
            with SessionLocal() as db:
                seed_database(db)
                db.commit()
    yield


app = FastAPI(title="ФСП Вектор API", version="0.1.0",
              description="Обратный найм по проверенным компетенциям. Демо-источники явно маркированы.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list({settings.frontend_url} | ({"http://127.0.0.1:3000"} if settings.local_demo else set())),
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", "X-CSRF-Token"], expose_headers=["X-Request-ID"])
app.add_middleware(BodyLimitMiddleware)


@app.middleware("http")
async def private_headers(request: Request, call_next):
    request.state.request_id = str(uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Server-Timing"] = f"api;dur={(time.perf_counter() - started) * 1000:.2f}"
    if request.url.path not in {"/health", "/ready"}:
        route = request.scope.get("route")
        # Log the server-defined route template, never user path values or query strings.
        safe_path = getattr(route, "path", "<unmatched>")
        safe_method = request.method if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"} else "OTHER"
        logger.info("request id=%s method=%s path=%s status=%s duration_ms=%.1f", request.state.request_id,
                    safe_method, safe_path, response.status_code, (time.perf_counter()-started)*1000)
    return response


@app.exception_handler(Problem)
async def domain_problem(request: Request, exc: Problem):
    return JSONResponse(status_code=exc.status, content={"type": f"urn:vector:problem:{exc.code.lower()}",
        "title": "Действие не выполнено", "status": exc.status, "detail": exc.detail,
        "code": exc.code, "request_id": getattr(request.state, "request_id", None)})


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(v) for v in item["loc"]), "message": item["msg"]} for item in exc.errors()]
    return JSONResponse(status_code=422, content={"type": "urn:vector:problem:validation", "title": "Проверьте форму",
        "status": 422, "detail": "Не все поля соответствуют требованиям.", "code": "VALIDATION_ERROR",
        "errors": errors, "request_id": getattr(request.state, "request_id", None)})


@app.exception_handler(ValidationError)
async def domain_validation(request: Request, exc: ValidationError):
    return await domain_problem(request, Problem(422, "VALIDATION_ERROR", "Не все поля соответствуют требованиям. Проверьте форму."))


@app.exception_handler(IntegrityError)
async def integrity_problem(request: Request, exc: IntegrityError):
    logger.warning("Integrity conflict request=%s", request.state.request_id)
    return await domain_problem(request, Problem(409, "DATA_CONFLICT", "Данные изменились или нарушают ограничения. Обновите страницу."))


@app.exception_handler(OperationalError)
async def database_problem(request: Request, exc: OperationalError):
    logger.error("Database transaction unavailable request=%s", request.state.request_id)
    return await domain_problem(request, Problem(503, "DATABASE_UNAVAILABLE", "Хранилище временно недоступно. Повторите действие позже."))


@app.exception_handler(Exception)
async def unexpected_problem(request: Request, exc: Exception):
    logger.error("Unexpected error request=%s class=%s", getattr(request.state,"request_id",None), type(exc).__name__)
    return await domain_problem(request, Problem(500, "INTERNAL_ERROR", "Не удалось выполнить действие. Сохраните номер запроса и повторите позже."))


@app.get("/health", tags=["Operations"])
@app.get("/api/v1/health", tags=["Operations"])
def health():
    from .judge import gateway_status
    judge = gateway_status()
    return {"status": "ok", "version": "0.1.0", "environment": "local_demo" if settings.local_demo else "production",
            "user_code_execution": "isolated_runner" if judge.get("available") else "unavailable_fail_closed", "judge": judge,
            "database": "postgresql" if engine.dialect.name == "postgresql" else "sqlite_portable"}


@app.get("/ready", tags=["Operations"])
def ready():
    with engine.connect() as connection:
        schema = schema_readiness(connection, require_migration=not settings.auto_create_schema)
    return {"status": "ready", "database": True, **schema}


app.include_router(auth.router, prefix="/api/v1")
# Mandatory feature imports fail startup instead of silently shrinking the product.
for module_name in ("candidate", "assessment", "employer", "hiring", "jobs", "platform"):
    module = importlib.import_module(f"app.{module_name}")
    app.include_router(module.router, prefix="/api/v1")

from .contracts import install_openapi
install_openapi(app)
for module_name in ("oidc", "judge"):
    try:
        module = importlib.import_module(f"app.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name == f"app.{module_name}":
            continue
        raise
    app.include_router(module.router, prefix="/api/v1")
