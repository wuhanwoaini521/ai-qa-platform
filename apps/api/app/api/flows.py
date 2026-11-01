from __future__ import annotations

from fastapi import APIRouter, Depends
from project_model.models import User

from app.api.authz import get_current_user
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
