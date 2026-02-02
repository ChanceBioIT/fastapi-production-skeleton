from __future__ import annotations

from typing import Optional
from email.message import EmailMessage

from framework.config import settings
from framework.logging.logger import get_logger

logger = get_logger("notifier")


async def notify_task_completed(
    email_to: Optional[str],
    job_id: str,
    task_type: str,
    job_name: Optional[str] = None,
    tenant_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> bool:
    """
    Task completion notification.
    - email_to empty: do not send, return False
    - NOTIFICATION_DRIVER=mock: log only, return True
    - NOTIFICATION_DRIVER=email: send via SMTP
    """
    if not email_to:
        return False

    driver = (settings.NOTIFICATION_DRIVER or "mock").lower()

    subject = f"[{settings.APP_NAME}] Task completed - {job_name or job_id}"
    lines = [
        "Your task has been completed.",
        "",
        f"- job_id: {job_id}",
        f"- task_type: {task_type}",
    ]
    if job_name:
        lines.append(f"- job_name: {job_name}")
    if tenant_id is not None:
        lines.append(f"- tenant_id: {tenant_id}")
    if user_id is not None:
        lines.append(f"- user_id: {user_id}")
    body = "\n".join(lines) + "\n"

    if driver == "mock":
        logger.info(
            f"[MOCK] send task completion email to={email_to} "
            f"job_id={job_id} task_type={task_type} job_name={job_name!r}"
        )
        return True

    if driver != "email":
        logger.warning(f"Unsupported NOTIFICATION_DRIVER={settings.NOTIFICATION_DRIVER!r}, skip sending")
        return False

    # email driver
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD missing), skip sending")
        return False

    msg = EmailMessage()
    msg["From"] = settings.SMTP_USER
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        import aiosmtplib

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT or 587,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info(f"Task completion email sent to={email_to} job_id={job_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send email to={email_to} job_id={job_id}: {str(e)}")
        return False

