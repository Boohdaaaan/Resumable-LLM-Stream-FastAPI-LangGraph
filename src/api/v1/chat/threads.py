from datetime import datetime

from sqlalchemy import select

from fastapi import APIRouter

from src.database.checkpointer import Checkpoint
from src.database.session import get_session
from src.schema.chat import ThreadSchema

router = APIRouter()


@router.get(
    "",
    description="Get list of all user's threads.",
    response_model=list[ThreadSchema],
)
async def get_threads():
    async with get_session() as session:
        checkpoints = await session.scalars(
            select(Checkpoint).distinct(Checkpoint.thread_id)
        )

    return [
        ThreadSchema(
            id=checkpoint.thread_id,
            chat_name=checkpoint.metadata_.get("chat_name", "New Chat"),
            last_activity_time=checkpoint.metadata_.get(
                "last_activity_time", datetime.now().isoformat()
            ),
        )
        for checkpoint in checkpoints
    ]
