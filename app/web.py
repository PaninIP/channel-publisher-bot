from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

WEBAPP_INDEX = Path(__file__).resolve().parent.parent / "webapp" / "index.html"

app = FastAPI(
    title="Channel Publisher Mini App",
    docs_url=None,
    redoc_url=None,
)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEBAPP_INDEX)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
