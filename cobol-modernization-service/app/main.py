"""Application entrypoint and FastAPI app factory."""

import app.env_bootstrap  # noqa: F401 — load service-root .env before routes/services

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.history import router as history_router
from app.api.routes.modernization import router as modernization_router
from app.api.routes.test_generator import router as test_generator_router
from app.api.routes.testing import router as testing_router
from app.api.routes.testing_retry import router as testing_retry_router
from app.db.history_session import init_history_db


def create_app() -> FastAPI:
    """
    Create the FastAPI application used by the COBOL modernization backend.

    Returns:
        A configured FastAPI application with parser, analysis, conversion,
        and validation routes mounted.

    Example:
        Input:
            create_app()
        Output:
            FastAPI(title="COBOL Modernization API")
    """

    app = FastAPI(title="COBOL Modernization API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:3001",
            "http://localhost:3001",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(modernization_router)
    app.include_router(history_router)
    app.include_router(testing_router)
    app.include_router(test_generator_router)
    app.include_router(testing_retry_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("startup")
    async def _log_process_env() -> None:
        import os

        from app.env_bootstrap import SERVICE_ROOT
        from app.services.behavioral_toolchain import clear_toolchain_cache

        clear_toolchain_cache()

        print(
            "[BOOT] COBOL modernization API startup pid=%s cwd=%s"
            % (os.getpid(), os.getcwd()),
            flush=True,
        )
        print("[BOOT] SERVICE_ROOT=%s" % SERVICE_ROOT, flush=True)
        print(
            "[BOOT] service .env exists=%s OPENAI_API_KEY set=%s GOOGLE_API_KEY set=%s OPENROUTER_API_KEY set=%s"
            % (
                (SERVICE_ROOT / ".env").is_file(),
                bool(os.getenv("OPENAI_API_KEY")),
                bool(os.getenv("GOOGLE_API_KEY")),
                bool(os.getenv("OPENROUTER_API_KEY")),
            ),
            flush=True,
        )
        init_history_db()
        print("[BOOT] conversion history DB initialized", flush=True)
        hist_paths = sorted(
            {getattr(r, "path", "") for r in app.routes if "history" in getattr(r, "path", "")},
        )
        print("[BOOT] mounted API paths (history): %s" % hist_paths, flush=True)

    return app


app = create_app()
