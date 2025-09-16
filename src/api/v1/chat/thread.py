import os
from functools import partial
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.ai.config import get_llm
from src.database.session import get_session
from src.database.checkpointer import Checkpoint
from src.ai.agent import GraphBuilder
from src.schema.chat import ThreadMessagesItemSchema
from sqlalchemy import select
from fastapi import Response

router = APIRouter()


class UpdateThreadNameRequest(BaseModel):
    chat_name: str


@router.get(
    "",
    description="Get a current thread details, including messages.",
    response_model=list[ThreadMessagesItemSchema],
)
async def get_thread(
    thread_id: UUID = Query(..., description="The thread ID to retrieve"),
    llm: BaseChatModel = Depends(partial(get_llm, "chat")),
):
    config = {"configurable": {"thread_id": str(thread_id)}}
    async with AsyncPostgresSaver.from_conn_string(
        conn_string=os.getenv("DATABASE_URI", ""),
    ) as checkpointer:
        graph = GraphBuilder(
            llm=llm,
            checkpointer=checkpointer,
            store=None,
        ).get_graph()

        state = await graph.aget_state(config, subgraphs=False)
        if not state or "messages" not in state.values:
            return []

        messages = []
        for message in state.values["messages"]:
            if isinstance(message, (HumanMessage, AIMessage)) and message.content:
                if isinstance(message.content, str):
                    messages.append(
                        ThreadMessagesItemSchema(
                            type=message.type, content=message.content
                        )
                    )
                elif isinstance(message.content, list):
                    messages.append(
                        ThreadMessagesItemSchema(
                            type=message.type,
                            content=message.content[0].get("text", ""),
                        )
                    )

        return messages


@router.delete("", description="Delete a current thread.")
async def delete_thread(
    thread_id: UUID = Query(..., description="The thread ID to delete"),
):
    async with AsyncPostgresSaver.from_conn_string(
        conn_string=os.getenv("DATABASE_URI", ""),
    ) as checkpointer:
        await checkpointer.adelete_thread(thread_id)
    return []


@router.patch("", description="Update the thread name (chat title).")
async def update_thread_name(
    request: UpdateThreadNameRequest,
    thread_id: UUID = Query(..., description="The thread ID to update"),
):
    async with get_session() as session:
        checkpoints = await session.scalars(
            select(Checkpoint).where(
                Checkpoint.thread_id == str(thread_id),
            )
        )

        for checkpoint in checkpoints:
            metadata = dict(checkpoint.metadata_ or {})
            metadata["chat_name"] = request.chat_name
            checkpoint.metadata_ = metadata

        await session.commit()

    return Response(status_code=204)
