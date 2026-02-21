"""
邮件服务
处理联系表单邮件发送
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.config import settings
from app.models.schemas import ContactForm


class EmailService:
    """
    邮件服务类
    处理 SMTP 邮件发送
    """

    def __init__(
        self,
        host: str = settings.SMTP_HOST,
        port: int = settings.SMTP_PORT,
        user: str = settings.SMTP_USER,
        password: str = settings.SMTP_PASSWORD,
        use_tls: bool = settings.SMTP_TLS,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self._server: Optional[smtplib.SMTP] = None

    def _connect(self) -> smtplib.SMTP:
        """建立 SMTP 连接"""
        server = smtplib.SMTP(self.host, self.port)
        if self.use_tls:
            server.starttls()
        if self.user and self.password:
            server.login(self.user, self.password)
        return server

    def send_contact_form(self, form_data: ContactForm) -> bool:
        """
        发送联系表单邮件

        Args:
            form_data: 联系表单数据

        Returns:
            发送是否成功
        """
        # 如果没有配置 SMTP，仅打印日志（开发环境）
        if not self.host:
            print(f"[MOCK EMAIL] Contact form from {form_data.name} ({form_data.email})")
            print(f"Subject: {form_data.subject}")
            print(f"Message: {form_data.message}")
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"【官网联系表单】{form_data.subject}"
            msg["From"] = self.user
            msg["To"] = settings.CONTACT_EMAIL_TO
            msg["Reply-To"] = form_data.email

            # 纯文本内容
            text_content = f"""
姓名：{form_data.name}
邮箱：{form_data.email}
电话：{form_data.phone or '未填写'}
公司：{form_data.company or '未填写'}
主题：{form_data.subject}

留言内容：
{form_data.message}
"""

            # HTML 内容
            html_content = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2>新的联系表单提交</h2>
    <table style="border-collapse: collapse; width: 100%;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">姓名</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{form_data.name}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">邮箱</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{form_data.email}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">电话</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{form_data.phone or '未填写'}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">公司</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{form_data.company or '未填写'}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">主题</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{form_data.subject}</td>
        </tr>
    </table>
    <h3>留言内容：</h3>
    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
        {form_data.message.replace(chr(10), '<br>')}
    </div>
</body>
</html>
"""

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            with self._connect() as server:
                server.send_message(msg)

            return True
        except Exception as e:
            print(f"邮件发送失败: {e}")
            return False


# 全局邮件服务实例
email_service = EmailService()
