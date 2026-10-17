from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from project_model.models import (
    AutomationBinding,
    AutomationBindingCreate,
    TestCase,
    TestCaseCreate,
    TestCaseUpdate,
)

from app.container import get_binding_service, get_test_case_service
from app.services.automation_binding_service import AutomationBindingService
from app.services.operation_trace import stream_operation
from app.services.test_case_service import TestCaseService

router = APIRouter(prefix="/test-cases", tags=["Test Cases"])


@router.post("/{case_id}/generate-automation/stream")
async def stream_automation_generation(case_id: str, service: AutomationBindingService = Depends(get_binding_service)):
    async def generate():
        binding, code = await service.generate_automation_draft(case_id)
        return {
            "test_case_id": case_id,
            "target_file": binding.file_path,
            "suggested_code": code,
            "grounded_knowledge": [],
            "page_objects": [],
        }

    return StreamingResponse(stream_operation(generate, "生成自动化草稿"), media_type="text/event-stream")


@router.get("", response_model=list[TestCase])
async def list_test_cases(
    project_id: str | None = None,
    service: TestCaseService = Depends(get_test_case_service),
):
    return await service.list_test_cases(project_id=project_id)


@router.post("", response_model=TestCase, status_code=status.HTTP_201_CREATED)
async def create_test_case(
    data: TestCaseCreate,
    service: TestCaseService = Depends(get_test_case_service),
):
    try:
        return await service.create_test_case(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/{case_id}", response_model=TestCase)
async def get_test_case(case_id: str, service: TestCaseService = Depends(get_test_case_service)):
    tc = await service.get_test_case(case_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test Case not found")
    return tc


@router.patch("/{case_id}", response_model=TestCase)
async def update_test_case(
    case_id: str,
    data: TestCaseUpdate,
    service: TestCaseService = Depends(get_test_case_service),
):
    try:
        tc = await service.update_test_case(case_id, data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if not tc:
        raise HTTPException(status_code=404, detail="Test Case not found")
    return tc


@router.get("/{case_id}/binding", response_model=AutomationBinding | None)
async def get_test_case_binding(
    case_id: str,
    service: AutomationBindingService = Depends(get_binding_service),
):
    return await service.get_binding(case_id)


@router.post("/{case_id}/binding", response_model=AutomationBinding)
async def create_or_update_binding(
    case_id: str,
    data: AutomationBindingCreate,
    service: AutomationBindingService = Depends(get_binding_service),
):
    if data.test_case_id != case_id:
        raise HTTPException(status_code=400, detail="Mismatched test_case_id in body")
    try:
        return await service.bind_test_case(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.delete("/{case_id}/binding")
async def delete_binding(
    case_id: str,
    service: AutomationBindingService = Depends(get_binding_service),
):
    success = await service.unbind_test_case(case_id)
    return {"success": success}


@router.post("/{case_id}/generate-automation")
async def generate_automation(
    case_id: str,
    service: AutomationBindingService = Depends(get_binding_service),
):
    try:
        binding, code = await service.generate_automation_draft(case_id)
        return {
            "status": "generated",
            "binding": binding,
            "code": code,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
