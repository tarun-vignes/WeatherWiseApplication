from fastapi import APIRouter

from app.ask import answer_question
from app.schemas import AskRequest, AskResponse

router = APIRouter(prefix="/api", tags=["ask"])


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    """Answer a plain-English weather question using live Open-Meteo data."""
    return await answer_question(body.question, body.latitude, body.longitude)
