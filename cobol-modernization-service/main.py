"""Compatibility entrypoint for the COBOL modernization FastAPI app."""

import os

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8010)),
        timeout_keep_alive=600,
        reload=False,
    )
