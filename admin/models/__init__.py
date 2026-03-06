"""
管理员服务数据模型
"""

from admin.models.admin_user import AdminUser
from admin.models.invitation_code import InvitationCode
from common.models.news import News

__all__ = ["AdminUser", "InvitationCode", "News"]
