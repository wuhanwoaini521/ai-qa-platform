from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from project_model.models import User

from app.api.authz import get_current_user
from app.container import get_flow_binding_service
from app.services.flow_binding_service import BindFlowRequest, FlowBindingService
from app.services.flow_compiler import FlowDocument, compile_flow

router = APIRouter(prefix="/flows", tags=["Flow Canvas"])


@router.post("/compile")
async def compile_flow_document(
    document: FlowDocument,
    _: User = Depends(get_current_user),
) -> dict:
    """Compile an authored flow into pytest source through the recorder generator.

    Authoring only: nothing is written and nothing executes. The caller decides whether to save the
    returned source into a workspace, which then uses the existing save/run/evidence path.
    """
    return compile_flow(document)


@router.post("/bind-case")
async def bind_flow_case(
    payload: BindFlowRequest,
    _: User = Depends(get_current_user),
    service: FlowBindingService = Depends(get_flow_binding_service),
) -> dict:
    """Bind a saved flow to a test case whose assertions carry the flow's criteria.

    Human-triggered: the caller saves the file first, then records the case identity. The case
    assertion panel derives run state from the nodeid stored on each assertion.
    """
    try:
        return await service.bind(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
