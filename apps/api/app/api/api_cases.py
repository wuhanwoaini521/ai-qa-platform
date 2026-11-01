from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from project_model.models import User

from app.api.authz import get_current_user
from app.api.project_acl import project_body_access, resource_body_access
from app.container import get_api_case_save_service
from app.services.api_case_persistence import ApiCaseSaveService, SaveApiCasePayload
from app.services.api_case_service import ApiCaseRequest, compile_api_case

router = APIRouter(prefix="/api-cases", tags=["API Cases"])


@router.post("/compile")
async def compile_api_case_endpoint(
    request: ApiCaseRequest,
    _: User = Depends(get_current_user),
) -> dict:
    """Compile a request spec into a pytest API case (authoring only: nothing is saved or run)."""
    return compile_api_case(request)


@router.post(
    "/save",
    dependencies=[Depends(project_body_access()), Depends(resource_body_access("requirement_id", "requirement"))],
)
async def save_api_case(
    payload: SaveApiCasePayload,
    _: User = Depends(get_current_user),
    service: ApiCaseSaveService = Depends(get_api_case_save_service),
) -> dict:
    """Save an authored API case: write the pytest file, create/refresh the case, bind the nodeid.

    Human-triggered. Criterion assertions are only stored when a requirement is chosen.
    """
    try:
        return await service.save(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
