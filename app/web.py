from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


WEBAPP_DIRECTORY = Path(__file__).resolve().parent.parent / "webapp"

app = FastAPI(
    title="Channel Publisher Mini App",
    docs_url=None,
    redoc_url=None,
)

app.mount(
    "/static",
    StaticFiles(directory=WEBAPP_DIRECTORY),
    name="static",
)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(
        WEBAPP_DIRECTORY / "index.html",
    )


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
