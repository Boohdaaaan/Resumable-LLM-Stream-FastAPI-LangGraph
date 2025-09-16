from fastapi import APIRouter

from src.api.v1.chat import chat
from src.api.v1.chat import thread
from src.api.v1.chat import threads

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(thread.router, prefix="/thread", tags=["Chat"])
api_router.include_router(threads.router, prefix="/threads", tags=["Chat"])
