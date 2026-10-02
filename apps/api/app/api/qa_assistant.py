from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from project_model.models import QAChatRequest, QAChatResponse

from app.api.event_stream import event_frame
from app.services.qa_assistant_service import QAAssistantService

router = APIRouter(prefix="/qa-assistant", tags=["QA Assistant Sidecar"])


def get_assistant_service() -> QAAssistantService:
    return QAAssistantService()


@router.post("/chat", response_model=QAChatResponse)
async def chat_assistant(
    request: QAChatRequest,
    service: QAAssistantService = Depends(get_assistant_service),
):
    return await service.handle_request(request)


@router.post("/chat/stream")
async def stream_chat_assistant(
    request: QAChatRequest,
    http_request: Request,
    service: QAAssistantService = Depends(get_assistant_service),
) -> StreamingResponse:
    async def events() -> AsyncGenerator[str, None]:
        stream = service.stream_request(request)
        try:
            async for event in stream:
                if await http_request.is_disconnected():
                    break
                yield event_frame(event.type, event)
        finally:
            await stream.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
