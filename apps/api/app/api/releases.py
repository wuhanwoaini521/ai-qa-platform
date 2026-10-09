from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from project_model.models import (
    Release,
    ReleaseCreate,
    ReleaseGateReport,
    ReleaseUpdate,
)

from app.container import get_release_service
from app.services.release_service import ReleaseService

router = APIRouter(prefix="/releases", tags=["Release Management & Quality Gate"])


@router.get("", response_model=list[Release])
async def list_releases(
    project_id: str | None = Query(default=None),
    service: ReleaseService = Depends(get_release_service),
):
    return await service.list_releases(project_id=project_id)


@router.post("", response_model=Release, status_code=status.HTTP_201_CREATED)
async def create_release(
    body: ReleaseCreate,
    service: ReleaseService = Depends(get_release_service),
):
    return await service.create_release(body)


@router.get("/{release_id}", response_model=Release)
async def get_release(
    release_id: str,
    service: ReleaseService = Depends(get_release_service),
):
    rel = await service.get_release(release_id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return rel


@router.patch("/{release_id}", response_model=Release)
async def update_release(
    release_id: str,
    body: ReleaseUpdate,
    service: ReleaseService = Depends(get_release_service),
):
    updated = await service.update_release(release_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return updated


@router.delete("/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_release(
    release_id: str,
    service: ReleaseService = Depends(get_release_service),
):
    deleted = await service.delete_release(release_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return None


@router.post("/{release_id}/gate-evaluate", response_model=ReleaseGateReport)
async def evaluate_release_gate(
    release_id: str,
    service: ReleaseService = Depends(get_release_service),
):
    try:
        return await service.evaluate_release_gate(release_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
