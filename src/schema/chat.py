from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="The message content from the user")
    thread_id: UUID = Field(
        default_factory=uuid4, description="The thread ID for the conversation"
    )


class ThreadMessagesItemSchema(BaseModel):
    type: Literal["ai", "human"]
    content: str


class ThreadMessagesResponse(BaseModel):
    messages: list[ThreadMessagesItemSchema]


class ThreadSchema(BaseModel):
    id: UUID
    chat_name: str
    last_activity_time: str
