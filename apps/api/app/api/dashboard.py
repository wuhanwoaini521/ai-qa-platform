from fastapi import APIRouter, Depends
from project_model.models import DashboardStats

from app.container import get_dashboard_service
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(service: DashboardService = Depends(get_dashboard_service)):
    return await service.get_stats()
