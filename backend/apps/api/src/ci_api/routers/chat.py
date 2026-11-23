"""Ask: graph-grounded chat over SSE."""

from __future__ import annotations

from fastapi import APIRouter, Response
from sse_starlette.sse import EventSourceResponse

from ci_ai import chat_stream
from ci_api.deps import pid
from ci_api.schemas import ChatBody

router = APIRouter()


@router.post("/projects/{project_ref:path}/chat")
async def chat(project_ref: str, body: ChatBody, response: Response) -> EventSourceResponse:
    project_id = pid(project_ref)
    response.headers["X-CI-Mode"] = "graph-tools-rag"
    history = [{"role": m.role, "content": m.content} for m in body.conversation_history]

    async def event_generator():
        # events: message (markdown text), tool, citations, done, error — see ci_ai.agent
        async for event in chat_stream(project_id, body.message, body.focus_node_id, conversation_history=history):
            yield event

    return EventSourceResponse(event_generator())
