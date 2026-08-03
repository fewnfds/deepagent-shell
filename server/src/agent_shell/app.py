from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent_shell.api.routes import build_router
from agent_shell.api.agent_configs import build_agent_config_router
from agent_shell.api.agent_sessions import build_agent_session_router
from agent_shell.api.automation import build_automation_router
from agent_shell.api.errors import localized_error_detail
from agent_shell.api.system import build_system_router
from agent_shell.api.api_server import ApiServerEventHub, build_api_server_router
from agent_shell.api.event_feed import build_event_feed_router
from agent_shell.api.runtime_diagnostics import build_runtime_diagnostics_router
from agent_shell.api.file_manager import build_file_manager_router
from agent_shell.api.provider_integrations import build_provider_integrations_router
from agent_shell.api.system_settings import build_system_settings_router
from agent_shell.api.validation import build_validation_router
from agent_shell.provider_http import ProviderHttpClients
from agent_shell.provider_secrets import ProviderSecretResolver
from agent_shell.runtime.request_snapshot import RequestSnapshotRuntime
from agent_shell.settings import Settings, SettingsError, get_settings
from agent_shell.runtime.interception import InterceptionTestController
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.event_feed import EventFeedService
from agent_shell.redaction import redact_for_boundary
from agent_shell.readiness import ReadinessService
from agent_shell.security_events import SecurityEventLogger
from agent_shell.security import (
    ApiKeyPolicyError,
    ScopeAuthenticationMiddleware,
    TrustedProxyHeadersMiddleware,
    validate_api_key_policy,
)
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.automation import AutomationStore
from agent_shell.storage.agent_sessions import AgentSessionStore
from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.blocks import BlockStore
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.history_retention import HistoryRetentionStore
from agent_shell.storage.runtime_controls import RuntimeControlSettingsStore
from agent_shell.storage.runtime_diagnostics import RuntimeDiagnosticStore
from agent_shell.storage.system_log_settings import MIB_BYTES, SystemLogSettingsStore
from agent_shell.storage.event_feed import EventFeedStore
from agent_shell.validation.service import ConfigurationValidationService
from agent_shell.automation.validation import AutomationValidationService
from agent_shell.file_manager import FileManagerService
from agent_shell.system_settings import SystemSettingsService
from agent_shell.storage.permissions import secure_directory, secure_file


def create_app(
    *,
    settings: Settings | None = None,
    serve_frontend: bool | None = None,
) -> FastAPI:
    application_home = (
        settings.application_home if settings is not None else Path.cwd().resolve()
    )
    if settings is None:
        settings = get_settings(application_home=application_home)
    settings.ensure_directories()

    environment_permissions = ()
    environment_path = settings.environment_file
    if environment_path.exists():
        environment_permission = secure_file(environment_path)
        if not environment_permission.enforced:
            raise SettingsError(
                ("data/config/agent-shell.env",),
                "Restrict the management settings file to the service account.",
            )
        environment_permissions = (environment_permission,)
    custom_tools_dir = settings.resolved_custom_tools_dir()
    custom_middlewares_dir = settings.resolved_custom_middlewares_dir()
    automation_scripts_dir = settings.resolved_automation_scripts_dir()
    skills_dir = settings.resolved_skills_dir()

    runtime_dir = settings.resolved_runtime_dir()
    logs_dir = settings.resolved_logs_dir()
    runtime_permissions = tuple(
        secure_directory(path)
        for path in (
            runtime_dir,
            runtime_dir / "cache",
            runtime_dir / "tmp",
            runtime_dir / "home",
        )
    )
    database = SQLiteDatabase(settings.resolved_database_path())
    system_log_settings = SystemLogSettingsStore(database)
    event_logger = SecurityEventLogger(
        logs_dir,
        max_bytes=system_log_settings.snapshot()["max_size_mib"] * MIB_BYTES,
    )
    history_retention = HistoryRetentionStore(database)
    runtime_control_settings = RuntimeControlSettingsStore(database)
    runtime_diagnostic_store = RuntimeDiagnosticStore(database, history_retention)
    block_store = BlockStore(database, event_logger)
    config_store = AgentConfigStore(database, event_logger)
    automation_store = AutomationStore(database, event_logger)
    automation_validation = AutomationValidationService(
        scripts_dir=automation_scripts_dir
    )
    configuration_validation = ConfigurationValidationService(
        block_store,
        config_store,
        automation_store,
        automation_validation,
        custom_tools_dir=custom_tools_dir,
    )
    api_server_store = ApiServerStore(database, event_logger, history_retention)
    if api_server_store.is_enabled():
        api_start_report = configuration_validation.validate_api_start()
        if not api_start_report.valid:
            api_server_store.set_enabled(False)
    try:
        validate_api_key_policy(settings, api_server_store.api_key())
    except ApiKeyPolicyError as exc:
        raise SettingsError(
            ("API Server API Key",), exc.safe_message
        ) from None
    agent_session_store = AgentSessionStore(database, history_retention)
    api_server_events = ApiServerEventHub()
    event_logger.set_publisher(api_server_events.publish_nowait)
    runtime_diagnostics = RuntimeDiagnostics(
        api_server_events.publish_nowait,
        store=runtime_diagnostic_store,
        control_settings=runtime_control_settings,
    )
    event_logger.set_failure_reporter(
        lambda exc, request_id: runtime_diagnostics.observation_error(
            exc,
            request_id=request_id,
            model="",
            agent_name="",
            code="security_event_record_failed",
        )
    )
    interception_tests = InterceptionTestController(runtime_control_settings)
    event_feed = EventFeedService(
        EventFeedStore(database),
        event_logger,
        runtime_diagnostics,
        system_log_settings,
    )
    secret_resolver = ProviderSecretResolver(database)
    provider_http_clients = ProviderHttpClients()
    file_manager = FileManagerService(
        {
            "files": settings.resolved_files_dir(),
            "skills": skills_dir,
            "custom_tools": custom_tools_dir,
            "custom_middlewares": custom_middlewares_dir,
            "automation_scripts": automation_scripts_dir,
        },
        settings.resolved_runtime_dir() / "tmp",
    )
    system_settings = SystemSettingsService(settings, api_server_store.api_key)
    agent_runtime = RequestSnapshotRuntime(
        database,
        custom_tools_dir=custom_tools_dir,
        automation_scripts_dir=automation_scripts_dir,
        runtime_dir=runtime_dir,
        skills_dir=skills_dir,
        diagnostics=runtime_diagnostics,
        provider_http_clients=provider_http_clients,
    )

    frontend_dir = Path(__file__).parent / "frontend_dist"
    frontend_available = (
        (frontend_dir / "index.html").is_file()
        and (frontend_dir / "assets").is_dir()
    )
    if serve_frontend is None:
        serve_frontend = frontend_available
    elif serve_frontend and not frontend_available:
        raise RuntimeError(
            "The production frontend build is missing. Build the frontend before "
            "starting a packaged Agent Shell instance."
        )
    startup_permission_statuses = (
        *environment_permissions,
        *runtime_permissions,
        database.directory_permission,
        *database.file_permissions,
        *event_logger.permission_statuses,
    )
    readiness = ReadinessService(
        settings=settings,
        startup_permission_statuses=startup_permission_statuses,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        event_logger.emit(
            "security_configuration_loaded",
            {
                "deployment_mode": settings.deployment_mode,
                "management_scope": "configured",
                "api_scope": (
                    "configured"
                    if api_server_store.api_key() is not None
                    else "unavailable"
                ),
                "trusted_proxy": bool(settings.trusted_proxy_cidrs),
            },
        )
        event_logger.emit(
            "service_started", {"deployment_mode": settings.deployment_mode}
        )
        try:
            yield
        finally:
            try:
                await provider_http_clients.aclose()
            finally:
                event_logger.emit(
                    "service_stopped", {"reason": "application_shutdown"}
                )
                runtime_diagnostics.close()

    app = FastAPI(
        title=settings.app_name,
        description="Agent configuration shell with OpenAI-compatible Primary execution.",
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    def record_management_failure(
        request: Request,
        *,
        status_code: int,
        detail: object,
    ) -> None:
        if request.url.path != "/api" and not request.url.path.startswith("/api/"):
            return
        code = "request_failed"
        issue_count = 0
        if isinstance(detail, dict):
            code = str(detail.get("code", code))
            validation = detail.get("validation")
            issues = (
                validation.get("issues", [])
                if isinstance(validation, dict)
                else detail.get("issues", [])
            )
            issue_count = len(issues) if isinstance(issues, list) else 0
        event_logger.emit(
            "management_request_failed",
            {
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "code": code,
                "issue_count": issue_count,
            },
        )

    @app.exception_handler(HTTPException)
    async def safe_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        headers = dict(exc.headers or {})
        request_id = getattr(request.state, "request_id", "")
        if request_id:
            headers["X-Request-ID"] = request_id
        detail = redact_for_boundary("http-error", exc.detail)
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            if not isinstance(detail, dict) or not isinstance(
                detail.get("message_key"), str
            ):
                detail = localized_error_detail(
                    code=(
                        str(detail.get("code", "request_failed"))
                        if isinstance(detail, dict)
                        else "request_failed"
                    ),
                    message_key="errors.requestFailed",
                    message="The management request failed.",
                )
        record_management_failure(
            request,
            status_code=exc.status_code,
            detail=detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={"detail": detail},
        )

    @app.exception_handler(RequestValidationError)
    async def safe_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_errors = [
            {
                key: error[key]
                for key in ("type", "loc", "msg")
                if key in error
            }
            for error in exc.errors()
        ]
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            detail: object = {
                **localized_error_detail(
                    code="request_validation_failed",
                    message_key="errors.requestValidationFailed",
                    message="The management request payload is invalid.",
                    message_args={"count": len(safe_errors)},
                ),
                "issues": safe_errors,
            }
        else:
            detail = safe_errors
        record_management_failure(request, status_code=422, detail=detail)
        return JSONResponse(
            status_code=422,
            headers={"X-Request-ID": getattr(request.state, "request_id", "")},
            content={
                "detail": redact_for_boundary(
                    "http-error",
                    detail,
                )
            },
        )

    @app.exception_handler(Exception)
    async def safe_internal_error(request: Request, exc: Exception) -> JSONResponse:
        runtime_diagnostics.runtime_error(
            exc,
            request_id=getattr(request.state, "request_id", ""),
            model="",
            agent_name="",
            code="internal_error",
        )
        request_id = getattr(request.state, "request_id", "")
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            content: dict[str, object] = {
                "detail": localized_error_detail(
                    code="internal_error",
                    message_key="errors.internalError",
                    message="An internal management operation failed.",
                ),
                "request_id": request_id,
            }
        else:
            content = {
                "error": {
                    "message": "An internal operation failed.",
                    "type": "internal_error",
                    "param": None,
                    "code": "internal_error",
                },
                "request_id": request_id,
            }
        record_management_failure(
            request,
            status_code=500,
            detail=content.get("detail") or content.get("error") or {},
        )
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": request_id},
            content=content,
        )
    app.state.settings = settings
    app.state.startup_storage_permissions = startup_permission_statuses
    app.state.security_events = event_logger
    app.state.agent_runtime = agent_runtime
    app.state.interception_tests = interception_tests
    app.state.runtime_diagnostics = runtime_diagnostics
    app.state.runtime_diagnostic_store = runtime_diagnostic_store
    app.state.agent_sessions = agent_session_store
    app.state.api_server_store = api_server_store
    app.state.provider_http_clients = provider_http_clients
    app.state.event_feed = event_feed
    app.state.system_log_settings = system_log_settings
    app.add_middleware(
        ScopeAuthenticationMiddleware,
        settings=settings,
        api_key_provider=api_server_store.api_key,
        event_logger=event_logger,
    )
    if settings.trusted_proxy_cidrs:
        app.add_middleware(
            TrustedProxyHeadersMiddleware,
            trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
        )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization", "Content-Type", "X-Request-ID", "X-Agent-Session-ID"
            ],
            expose_headers=["X-Request-ID", "X-Agent-Session-ID"],
            max_age=600,
        )
    app.include_router(build_system_router(readiness))
    app.include_router(
        build_router(
            block_store,
            config_store,
            custom_tools_dir,
            custom_middlewares_dir,
            skills_dir,
            secret_resolver,
            configuration_validation,
            provider_http_clients,
        )
    )
    app.include_router(
        build_agent_config_router(
            config_store,
            configuration_validation,
        )
    )
    app.include_router(build_validation_router(configuration_validation))
    app.include_router(
        build_automation_router(
            automation_store,
            config_store,
            automation_validation,
            automation_scripts_dir,
        )
    )
    app.include_router(build_agent_session_router(agent_session_store))
    app.include_router(build_runtime_diagnostics_router(runtime_diagnostics))
    app.include_router(
        build_event_feed_router(
            event_feed,
            api_server_store,
            api_server_events,
            interception_tests,
        )
    )
    app.include_router(build_file_manager_router(file_manager))
    app.include_router(build_provider_integrations_router())
    app.include_router(build_system_settings_router(system_settings))
    app.include_router(
        build_api_server_router(
            api_server_store,
            config_store,
            agent_runtime,
            settings,
            api_server_events,
            interception_tests,
            runtime_diagnostics,
            agent_session_store,
            configuration_validation,
        )
    )

    if serve_frontend:
        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:
            return RedirectResponse(url="/admin", status_code=307)

        assets_dir = frontend_dir / "assets"
        app.mount("/admin/assets", StaticFiles(directory=assets_dir), name="admin-assets")

        @app.get("/admin", include_in_schema=False)
        async def admin_page() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

        @app.get("/admin/favicon.ico", include_in_schema=False)
        async def admin_favicon() -> FileResponse:
            return FileResponse(frontend_dir / "favicon.ico", media_type="image/x-icon")

    return app
