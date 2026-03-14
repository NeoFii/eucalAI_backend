"""Legacy dashboard endpoints for admin control-plane stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_current_admin, get_db_session
from admin_service.models import AdminUser
from admin_service.services.identity_client import IdentityClientService
from admin_service.services.invitation_service import InvitationCodeService

router = APIRouter(tags=["绠＄悊鍛樹华琛ㄧ洏"])


@router.get("/dashboard/stats", summary="Get dashboard stats")
async def get_stats(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    del current_admin
    code_stats = await InvitationCodeService.get_stats(db)
    total_users = await IdentityClientService.fetch_total_users()
    return {
        "code": 200,
        "message": "鑾峰彇鎴愬姛",
        "data": {
            "total_users": total_users,
            "total_invitation_codes": code_stats["total"],
            "used_invitation_codes": code_stats["used"],
            "valid_invitation_codes": code_stats["valid"],
        },
    }

