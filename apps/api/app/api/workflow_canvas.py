from fastapi import APIRouter, Depends, Query
from project_model.models import User
from project_model.workflow_canvas import WorkflowCanvas

from app.api.authz import get_current_user
from app.api.project_acl import enforce_project_access
from app.api.tasks import get_task_command_service
from app.container import get_workflow_canvas_service
from app.services.workflow_canvas_service import WorkflowCanvasService

router = APIRouter(prefix="/projects", tags=["Workflow Canvas"])


@router.get("/{project_id}/workflow-canvas", response_model=WorkflowCanvas)
async def get_workflow_canvas(
    project_id: str,
    requirement_id: str | None = Query(default=None, max_length=36),
    user: User = Depends(get_current_user),
    service: WorkflowCanvasService = Depends(get_workflow_canvas_service),
    commands=Depends(get_task_command_service),
):
    """Read-only projection of this project's real records.

    Nothing here executes: the canvas only reads, and every node keeps a link back to
    the page that owns it.
    """
    await enforce_project_access(user, project_id)
    return await service.build(project_id, str(user.id), tasks=commands, requirement_id=requirement_id)
