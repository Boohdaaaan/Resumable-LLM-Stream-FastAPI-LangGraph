import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

load_dotenv()

from src.api.v1.api import api_router  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Chat API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Serve SPA at root and static assets under /static
frontend_dir = Path(__file__).parent / "src" / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
async def root():
    if frontend_dir.exists():
        return FileResponse(str(frontend_dir / "index.html"))
    return {"status": "online", "message": "Chat API is running"}


app.include_router(api_router, prefix="")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
