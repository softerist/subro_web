# backend/app/services/email_service.py
"""
Email service for sending transactional emails.
Supports Mailgun API.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> bool:
    """
    Send an email using Mailgun API.

    Returns True if email was sent successfully, False otherwise.
    """
    if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN:
        logger.warning(f"Mailgun not configured. Would have sent email to {to_email}: {subject}")
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages",
                auth=("api", settings.MAILGUN_API_KEY),
                data={
                    "from": f"{settings.MAILGUN_FROM_NAME} <{settings.MAILGUN_FROM_EMAIL}>",
                    "to": to_email,
                    "subject": subject,
                    "text": text_content or "",
                    "html": html_content,
                },
            )

            if response.status_code == 200:
                logger.info(f"Email sent successfully to {to_email}: {subject}")
                return True
            else:
                logger.error(f"Mailgun API error: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
        return False


async def send_password_reset_email(email: str, token: str) -> bool:
    """Send password reset email with reset link."""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    subject = "Reset Your Password"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">Subro Web</h1>
        </div>
        <div style="padding: 30px; background: #f9fafb;">
            <h2 style="color: #1f2937;">Reset Your Password</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                You requested to reset your password. Click the button below to create a new password:
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}"
                   style="background: #3b82f6; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Reset Password
                </a>
            </div>
            <p style="color: #6b7280; font-size: 14px;">
                If you didn't request this, you can safely ignore this email.
            </p>
            <p style="color: #6b7280; font-size: 14px;">
                This link will expire in 1 hour.
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #9ca3af; font-size: 12px; text-align: center;">
                If the button doesn't work, copy and paste this URL into your browser:<br>
                <a href="{reset_url}" style="color: #3b82f6;">{reset_url}</a>
            </p>
        </div>
    </body>
    </html>
    """

    text_content = f"""
Reset Your Password

You requested to reset your password. Click the link below to create a new password:

{reset_url}

If you didn't request this, you can safely ignore this email.

This link will expire in 1 hour.
    """

    return await send_email(email, subject, html_content, text_content)
