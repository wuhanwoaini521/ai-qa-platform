from fastapi import APIRouter, Depends
from project_model.models import QAChatRequest, QAChatResponse

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
