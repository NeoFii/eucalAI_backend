"""
联系表单 API 端点
处理用户提交的咨询和反馈
"""

from fastapi import APIRouter, status

from app.models.schemas import ContactForm, ContactFormResponse
from app.services.email_service import email_service

router = APIRouter()


@router.post(
    "",
    response_model=ContactFormResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交联系表单"
)
async def submit_contact_form(form_data: ContactForm) -> ContactFormResponse:
    """
    提交联系表单

    - **name**: 姓名（2-50字符）
    - **email**: 邮箱地址
    - **phone**: 电话（可选）
    - **company**: 公司名称（可选）
    - **subject**: 主题
    - **message**: 留言内容（10-2000字符）
    """
    # 发送邮件通知
    email_sent = email_service.send_contact_form(form_data)

    return ContactFormResponse(
        code="success",
        message="您的留言已收到，我们会尽快与您联系！",
        data={
            "email_sent": email_sent,
            "name": form_data.name,
            "subject": form_data.subject,
        }
    )


@router.get("/info", summary="获取联系信息")
async def get_contact_info():
    """
    获取公司联系信息
    """
    return {
        "code": "success",
        "data": {
            "company_name": "Eucal AI",
            "address": "北京市海淀区中关村科技园 Eucal AI 大厦",
            "phone": "400-888-8888",
            "email": "contact@eucal.ai",
            "business_hours": "周一至周五 9:00-18:00",
            "social_media": {
                "wechat": "company_official",
                "weibo": "@公司官方微博",
                "linkedin": "company-linkedin",
            }
        }
    }
