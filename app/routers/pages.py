from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas import MAX_WORDS, MIN_WORDS

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
router = APIRouter(include_in_schema=False)

# Pages are thin shells: data is loaded by app.js from the JSON API with the user's token.


def _page(request: Request, name: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(
        request, name, {"min_words": MIN_WORDS, "max_words": MAX_WORDS, **ctx}
    )


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _page(request, "grade.html", page="grade")


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return _page(request, "auth.html", page="login")


@router.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return _page(request, "auth.html", page="register")


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    return _page(request, "history.html", page="history")


@router.get("/history/{essay_id}", response_class=HTMLResponse)
async def essay_detail(request: Request, essay_id: int):
    return _page(request, "essay.html", page="history", essay_id=essay_id)
