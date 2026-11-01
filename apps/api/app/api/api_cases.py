from __future__ import annotations

from fastapi import APIRouter, Depends
from project_model.models import User

from app.api.authz import get_current_user
from app.services.api_case_service import ApiCaseRequest, compile_api_case

router = APIRouter(prefix="/api-cases", tags=["API Cases"])


@router.post("/compile")
async def compile_api_case_endpoint(
    request: ApiCaseRequest,
    _: User = Depends(get_current_user),
) -> dict:
    """Compile a request spec into a pytest API case (authoring only: nothing is saved or run)."""
    return compile_api_case(request)
