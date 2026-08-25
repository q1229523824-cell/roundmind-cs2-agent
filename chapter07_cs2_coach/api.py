"""CS2 智能复盘教练的 FastAPI 与网页入口。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from chapter07_cs2_coach.models import (
    AnalysisRequest,
    AnalysisResponse,
    CoachChatRequest,
    CoachChatResponse,
    DemoJobResponse,
    DemoPlayerSelection,
    MatchRecord,
    PlayerProfileResponse,
)
from chapter07_cs2_coach.demo_jobs import (
    DemoJobManager,
    DemoJobStateError,
    DemoQueueFullError,
)
from chapter07_cs2_coach.distributed_jobs import distributed_manager_from_environment
from chapter07_cs2_coach.runtime import CS2CoachRuntime
from chapter07_cs2_coach.database import MatchOwnershipConflictError
from chapter07_cs2_coach.auth import (
    AuthConfigurationError,
    AuthService,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_DEMO_MB = 500
MAX_DEMO_BYTES = MAX_DEMO_MB * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
DEFAULT_QUESTION = "请综合分析这场比赛，找出最值得优先改进的问题。"


def _bounded_positive_int(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} 必须是整数。") from error
    if not 1 <= value <= maximum:
        raise RuntimeError(f"{name} 必须在 1 到 {maximum} 之间。")
    return value


def _cors_origins() -> list[str]:
    configured = os.getenv("ROUNDMIND_CORS_ORIGINS", "")
    if configured.strip():
        return [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]
    return [
        "https://roundmind-cs2-coach.kclespark.chatgpt.site",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]


def create_app(
    runtime: CS2CoachRuntime | None = None,
    demo_jobs: DemoJobManager | None = None,
    auth_service: AuthService | None = None,
) -> FastAPI:
    runtime = runtime or CS2CoachRuntime.create()
    app = FastAPI(
        title="RoundMind CS2 智能复盘教练",
        version="1.0.0",
        description="用受控 Agent 工作流把比赛事实转化为可追溯的训练建议。",
    )
    app.state.runtime = runtime
    app.state.auth = auth_service or AuthService.from_environment()
    if demo_jobs is not None:
        app.state.demo_jobs = demo_jobs
    elif os.getenv("ROUNDMIND_JOB_BACKEND", "local").strip().lower() == "celery":
        app.state.demo_jobs = distributed_manager_from_environment()
    else:
        app.state.demo_jobs = DemoJobManager(
            runtime,
            max_pending_jobs=_bounded_positive_int(
                "ROUNDMIND_MAX_PENDING_JOBS", 2, 100
            ),
            max_workers=_bounded_positive_int("ROUNDMIND_DEMO_WORKERS", 1, 8),
        )
    @app.middleware("http")
    async def reject_demo_upload_when_full(request: Request, call_next):
        # 中间件在 multipart 解析前运行，避免队列已满时仍把大文件落到临时磁盘。
        if request.method == "POST" and request.url.path == "/api/demo-jobs":
            try:
                app.state.demo_jobs.ensure_capacity()
            except DemoQueueFullError as error:
                return JSONResponse(
                    status_code=429,
                    content={"detail": str(error)},
                    headers={"Retry-After": "30"},
                )
        return await call_next(request)

    # 后添加的 CORS 位于准入中间件外层，429 也能被跨域前端正常读取。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.mount("/static", StaticFiles(directory=WEB_DIRECTORY), name="static")
    bearer = HTTPBearer(auto_error=False)

    @app.exception_handler(MatchOwnershipConflictError)
    async def ownership_conflict(_request, error: MatchOwnershipConflictError):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    def current_identity(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> UserResponse | None:
        if not app.state.auth.enabled:
            return None
        if credentials is None:
            raise HTTPException(status_code=401, detail="请先登录。")
        try:
            return app.state.auth.verify_token(credentials.credentials)
        except InvalidCredentialsError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    @app.post("/api/auth/register", response_model=TokenResponse, tags=["auth"])
    def register(request: RegisterRequest) -> TokenResponse:
        try:
            return app.state.auth.register(request.email, request.password)
        except EmailAlreadyExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AuthConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/api/auth/login", response_model=TokenResponse, tags=["auth"])
    def login(request: LoginRequest) -> TokenResponse:
        try:
            return app.state.auth.login(request.email, request.password)
        except InvalidCredentialsError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except AuthConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/api/auth/me", response_model=UserResponse, tags=["auth"])
    def me(identity: UserResponse | None = Depends(current_identity)) -> UserResponse:
        if identity is None:
            raise HTTPException(status_code=503, detail="登录功能尚未启用。")
        return identity

    @app.get("/", include_in_schema=False)
    def homepage() -> FileResponse:
        return FileResponse(WEB_DIRECTORY / "index.html")

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "service": "roundmind-cs2-coach",
            "version": os.getenv("RENDER_GIT_COMMIT", "local")[:12],
            "storage": runtime.repository.backend_name,
            "demo_storage": app.state.demo_jobs.object_store.backend_name,
            "job_backend": getattr(app.state.demo_jobs, "store", None).backend_name
            if hasattr(app.state.demo_jobs, "store")
            else "memory",
            "auth": "required" if app.state.auth.enabled else "disabled",
            "pending_jobs": app.state.demo_jobs.pending_count(),
            "max_pending_jobs": app.state.demo_jobs.max_pending_jobs,
        }

    @app.get("/ready", tags=["system"])
    def ready() -> dict[str, str]:
        try:
            runtime.repository.check_connection()
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="数据库暂时不可用。",
            ) from error
        return {"status": "ready", "storage": runtime.repository.backend_name}

    @app.get("/api/matches", response_model=list[MatchRecord], tags=["matches"])
    def list_matches(
        identity: UserResponse | None = Depends(current_identity),
    ) -> list[MatchRecord]:
        return (
            runtime.repository.list_for_owner(identity.id)
            if identity
            else runtime.repository.list()
        )

    @app.post("/api/matches", response_model=MatchRecord, tags=["matches"])
    def add_match(
        match: MatchRecord, identity: UserResponse | None = Depends(current_identity)
    ) -> MatchRecord:
        return runtime.add_match(match, identity.id if identity else None)

    @app.post("/api/upload-json", response_model=MatchRecord, tags=["matches"])
    async def upload_json(
        file: UploadFile = File(...),
        identity: UserResponse | None = Depends(current_identity),
    ) -> MatchRecord:
        if not file.filename or not file.filename.lower().endswith(".json"):
            raise HTTPException(status_code=400, detail="MVP 目前只接受 .json 比赛文件。")
        content = await file.read(MAX_JSON_BYTES + 1)
        if len(content) > MAX_JSON_BYTES:
            raise HTTPException(status_code=413, detail="JSON 文件不能超过 2 MB。")
        try:
            payload = json.loads(content.decode("utf-8"))
            match = MatchRecord.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
            raise HTTPException(status_code=422, detail=f"比赛文件格式无效：{error}") from error
        return runtime.add_match(match, identity.id if identity else None)

    @app.post(
        "/api/demo-jobs",
        response_model=DemoJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["demos"],
    )
    async def create_demo_job(
        file: UploadFile = File(...),
        player_name: str | None = Form(default=None, max_length=80),
        player_steamid: str | None = Form(default=None, max_length=32),
        question: str = Form(DEFAULT_QUESTION, min_length=1, max_length=1000),
        identity: UserResponse | None = Depends(current_identity),
    ) -> DemoJobResponse:
        filename = Path(file.filename or "").name
        if not filename.lower().endswith(".dem"):
            raise HTTPException(status_code=400, detail="只接受 .dem 格式的 CS2 Demo。")

        try:
            app.state.demo_jobs.ensure_capacity()
        except DemoQueueFullError as error:
            raise HTTPException(
                status_code=429,
                detail=str(error),
                headers={"Retry-After": "30"},
            ) from error

        temporary_path: Path | None = None
        size = 0
        first_bytes = b""
        try:
            with NamedTemporaryFile(prefix="roundmind-", suffix=".dem", delete=False) as output:
                temporary_path = Path(output.name)
                while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                    if not first_bytes:
                        first_bytes = chunk[:8]
                    size += len(chunk)
                    if size > MAX_DEMO_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Demo 文件不能超过 {MAX_DEMO_MB} MB。",
                        )
                    output.write(chunk)
            if first_bytes != b"PBDEMS2\x00":
                raise HTTPException(
                    status_code=422,
                    detail="文件头无效：这不是 CS2 Source 2 Demo。",
                )
            assert temporary_path is not None
            try:
                return app.state.demo_jobs.submit_upload(
                    path=temporary_path,
                    filename=filename,
                    player_name=player_name.strip() if player_name else None,
                    player_steamid=player_steamid.strip() if player_steamid else None,
                    question=question.strip(),
                    owner_id=identity.id if identity else None,
                )
            except DemoQueueFullError as error:
                raise HTTPException(status_code=429, detail=str(error)) from error
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get(
        "/api/demo-jobs/{job_id}",
        response_model=DemoJobResponse,
        tags=["demos"],
    )
    def get_demo_job(
        job_id: str, identity: UserResponse | None = Depends(current_identity)
    ) -> DemoJobResponse:
        try:
            return app.state.demo_jobs.get(job_id, identity.id if identity else None)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Demo 解析任务不存在。") from error

    @app.post(
        "/api/demo-jobs/{job_id}/player",
        response_model=DemoJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["demos"],
    )
    def select_demo_player(
        job_id: str,
        selection: DemoPlayerSelection,
        identity: UserResponse | None = Depends(current_identity),
    ) -> DemoJobResponse:
        try:
            return app.state.demo_jobs.select_player(
                job_id,
                player_name=selection.player_name.strip(),
                player_steamid=selection.player_steamid,
                question=selection.question.strip(),
                owner_id=identity.id if identity else None,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Demo 解析任务不存在。") from error
        except DemoJobStateError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/analyze", response_model=AnalysisResponse, tags=["agent"])
    def analyze(
        request: AnalysisRequest,
        identity: UserResponse | None = Depends(current_identity),
    ) -> AnalysisResponse:
        try:
            return runtime.analyze(
                match_id=request.match_id,
                question=request.question,
                owner_id=identity.id if identity else None,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/coach/chat", response_model=CoachChatResponse, tags=["coach"])
    def coach_chat(
        request: CoachChatRequest,
        identity: UserResponse | None = Depends(current_identity),
    ) -> CoachChatResponse:
        try:
            return runtime.coach_chat(
                player_steamid=request.player_steamid.strip(),
                map_name=request.map_name.strip(),
                question=request.question.strip(),
                conversation_history=[
                    item.model_dump() for item in request.conversation_history
                ],
                owner_id=identity.id if identity else None,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/player-profiles/{player_steamid}",
        response_model=PlayerProfileResponse,
        tags=["profiles"],
    )
    def player_profile(
        player_steamid: str,
        map_name: str | None = Query(default=None, max_length=80),
        identity: UserResponse | None = Depends(current_identity),
    ) -> PlayerProfileResponse:
        if not player_steamid.strip() or len(player_steamid) > 32:
            raise HTTPException(status_code=422, detail="SteamID 格式无效。")
        try:
            return runtime.player_profile(
                player_steamid=player_steamid.strip(),
                map_name=map_name.strip() if map_name else None,
                owner_id=identity.id if identity else None,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return app


app = create_app()
