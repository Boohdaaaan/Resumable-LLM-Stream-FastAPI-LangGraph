import os
import logging
from time import monotonic
from datetime import datetime
from functools import partial
from typing import AsyncGenerator
from uuid import uuid4, UUID
from fastapi import APIRouter, Depends, status, Response
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.ai.config import get_llm

from src.ai.agent import GraphBuilder
from src.schema.chat import ChatRequest
from fastapi.background import BackgroundTasks
from src.cache.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()

STREAM_TTL_SECONDS = int(os.getenv("STREAM_TTL_SECONDS", "900"))  # 15 minutes by default


def _format_sse_event(message_id: str, data: str, event: str = None) -> str:
    """Build a well-formed SSE event string.

    - Splits payload into lines and prefixes each with "data: ".
    - Adds optional event name.
    - Appends a blank line terminator as required by the SSE spec.
    """
    lines = data.split("\n")
    parts: list[str] = []
    parts.append(f"event: {event}")
    parts.append(f"id: {message_id}")
    for line in lines:
        parts.append(f"data: {line}")
    parts.append("")  # terminator
    return "\n".join(parts) + "\n"


async def generate_response(
    request: ChatRequest, llm: BaseChatModel, stream_id: str, thread_id: str, config: RunnableConfig
) -> None:
    r = get_redis()
    try:
        async with AsyncPostgresSaver.from_conn_string(
            conn_string=os.getenv("DATABASE_URI", ""),
        ) as checkpointer:
            await checkpointer.setup()
            graph = GraphBuilder(
                llm=llm,
                checkpointer=checkpointer,
                store=None,
            ).get_graph()

            events = graph.astream(
                {"messages": HumanMessage(content=request.message)},
                config,
                stream_mode="messages",
            )

            async for chunk, metadata in events:
                # New chunk
                if isinstance(chunk, AIMessageChunk) and chunk.content and metadata.get("langgraph_node", "") == "agent":
                    await r.xadd(stream_id, {"event": "chunk", "data": chunk.content})

                # New tool call
                if isinstance(chunk, AIMessageChunk) and chunk.tool_calls:
                    for tool_call in chunk.tool_calls:
                        tool_name = tool_call["name"].strip()
                        if tool_name:
                            await r.xadd(stream_id, {"event": "tool_call", "data": tool_name})

                # Message ended
                if chunk.response_metadata and chunk.response_metadata.get("finish_reason"):
                    msg_id = await r.xadd(
                        stream_id, {"event": "system", "data": "message_ended"}
                    )
                    await r.set(f"{stream_id}:message_ended", msg_id, ex=STREAM_TTL_SECONDS)

                # Touch TTLs for active stream
                await r.expire(thread_id, STREAM_TTL_SECONDS)
                await r.expire(stream_id, STREAM_TTL_SECONDS)
                await r.expire(f"{stream_id}:message_ended", STREAM_TTL_SECONDS)
                await r.expire(f"{stream_id}:status", STREAM_TTL_SECONDS)
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        await r.xadd(stream_id, {"event": "system", "data": "error"})
    finally:
        await r.xadd(stream_id, {"event": "system", "data": "end"})
        await r.set(f"{stream_id}:status", "completed", ex=STREAM_TTL_SECONDS)


@router.post("/message", status_code=status.HTTP_200_OK)
async def chat_message(
    request: ChatRequest,
    llm: BaseChatModel = Depends(partial(get_llm, "chat")),
    *,
    background_tasks: BackgroundTasks,
) -> None:
    config = {
        "configurable": {
            "thread_id": str(request.thread_id),
            "last_activity_time": datetime.now().isoformat(),
        }
    }

    r = get_redis()

    stream_id = str(uuid4())
    thread_id = str(request.thread_id)
    await r.set(f"{stream_id}:status", "running", ex=STREAM_TTL_SECONDS)
    await r.set(thread_id, stream_id, ex=STREAM_TTL_SECONDS)

    background_tasks.add_task(
        generate_response,
        request,
        llm,
        stream_id,
        thread_id,
        config,
    )

    return None


@router.get("/stream")
async def stream_tokens(thread_id: UUID):
    r = get_redis()
    STREAM_ID: str | None = await r.get(str(thread_id))
    if not STREAM_ID:
        return Response(status_code=204)

    status: str | None = await r.get(f"{STREAM_ID}:status")
    if not status or status == "completed":
        return Response(status_code=204)

    message_ended_id = await r.get(f"{STREAM_ID}:message_ended")

    async def get_chunks(last_id: str) -> AsyncGenerator[str, None]:
        last_ping_time = monotonic()
        while True:
            # Heartbeat ping to keep SSE connection alive
            current_time = monotonic()
            if current_time - last_ping_time >= 20:
                yield ": keepalive\n\n"
                last_ping_time = current_time

            messages = await r.xread(streams={STREAM_ID: last_id}, block=3000)

            if not messages:
                continue

            for _, msgs in messages:
                for msg_id, data in msgs:
                    yield _format_sse_event(
                        message_id=msg_id,
                        data=data["data"],
                        event=data["event"],
                    )

                    last_id = msg_id

                    if data["event"] == "system" and data["data"] == "end":
                        return

    return StreamingResponse(
        get_chunks(last_id=message_ended_id or "0"),
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
