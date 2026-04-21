"""Application entrypoint and FastAPI app factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.modernization import router as modernization_router


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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(modernization_router)
    return app


app = create_app()
