"""Compatibility entrypoint for the COBOL modernization FastAPI app."""

from app.core.config import load_config
from app.main import app

if __name__ == "__main__":
    import uvicorn

    config = load_config()
    uvicorn.run(app, host=config.host, port=config.port)
