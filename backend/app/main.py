import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config.config import settings
from backend.app.database.session import Base, engine, SessionLocal
from backend.app.simulator.seed_data import seed_database
from backend.app.models.recovery_case import RecoveryCase
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.recovery import router as recovery_router, batch_router
from backend.app.api.analytics import router as analytics_router
from backend.app.api.simulator import router as simulator_router
from backend.app.api.events import router as events_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    Base.metadata.create_all(bind=engine)
    # Check if database has cases; if empty, seed automatically
    db = SessionLocal()
    try:
        case_count = db.query(RecoveryCase).count()
        if case_count == 0:
            seed_database(db, n_cases=1000)
    finally:
        db.close()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Autonomous Revenue Recovery Platform for Razorpay Ideathon Track 3",
    version="1.0.0",
    lifespan=lifespan,
)

# Correlation ID and Request Tracking Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    corr_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid.uuid4().hex[:12]}"
    request.state.correlation_id = corr_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = corr_id
    return response

# Standardized Error Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    corr_id = getattr(request.state, "correlation_id", f"corr-{uuid.uuid4().hex[:12]}")
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        err_obj = exc.detail["error"]
        if not err_obj.get("correlation_id"):
            err_obj["correlation_id"] = corr_id
        return JSONResponse(status_code=exc.status_code, content={"error": err_obj})
    
    # Generic string or unnested detail
    code_map = {
        400: "VALIDATION_ERROR",
        404: "NOT_FOUND",
        409: "IDEMPOTENCY_CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
    }
    err_code = code_map.get(exc.status_code, "ERROR")
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": err_code,
                "message": msg,
                "details": {},
                "correlation_id": corr_id,
            }
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    corr_id = getattr(request.state, "correlation_id", f"corr-{uuid.uuid4().hex[:12]}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request payload or parameter validation failed.",
                "details": {"validation_errors": exc.errors()},
                "correlation_id": corr_id,
            }
        },
    )

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(recovery_router, prefix=settings.API_V1_STR)
app.include_router(batch_router, prefix=settings.API_V1_STR)
app.include_router(analytics_router, prefix=settings.API_V1_STR)
app.include_router(simulator_router, prefix=settings.API_V1_STR)
app.include_router(events_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {
        "status": "HEALTHY",
        "service": settings.PROJECT_NAME,
        "policy_version": settings.POLICY_VERSION,
        "agent_version": settings.AGENT_VERSION,
    }
