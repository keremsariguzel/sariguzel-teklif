from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.routes import router


app = FastAPI(
    title="Sarıgüzel Teklif | Endüstriyel Lazer Kesim SaaS",
    version="4.0.0",
)
app.include_router(router)

HTML_FILE = Path(__file__).parent / "templates" / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    return HTMLResponse(content=HTML_FILE.read_text(encoding="utf-8"))
