"""Outgoing email. SMTP in real deployments; a clearly-labelled console backend in development.

send_email() returns True only when the message was handed to the SMTP server successfully.
The console backend returns False so callers never report "email sent" when it wasn't.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("healthai.email")


class EmailNotConfigured(RuntimeError):
    pass


def smtp_configured() -> bool:
    s = get_settings()
    return s.email_backend == "smtp" and bool(s.smtp_host)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    s = get_settings()
    if s.email_backend == "console":
        if s.environment == "production":
            raise EmailNotConfigured("console email backend is not allowed in production")
        log.warning(
            "[EMAIL NOT SENT — console backend]\nTo: %s\nSubject: %s\n\n%s", to, subject, text
        )
        return False
    if not s.smtp_host:
        raise EmailNotConfigured("SMTP_HOST is not set")

    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    try:
        if s.smtp_use_ssl:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx, timeout=15)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        with server:
            if s.smtp_use_tls and not s.smtp_use_ssl:
                server.starttls(context=ctx)
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        log.error("SMTP delivery failed to %s: %s", to, e)
        if s.environment != "production":
            # Development convenience: keep the link usable when SMTP is misconfigured.
            log.warning("[EMAIL NOT SENT — SMTP failed]\nTo: %s\nSubject: %s\n\n%s", to, subject, text)
        return False
    return True


# ------------------------------------------------------------------ templates
def _wrap(title: str, body_html: str) -> str:
    return f"""<!doctype html><html><body style="font-family:system-ui,sans-serif;background:#f4f8fb;padding:24px">
<div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;padding:32px">
<h2 style="color:#0b5cab;margin-top:0">{title}</h2>{body_html}
<p style="color:#6b7280;font-size:12px;margin-top:32px">HealthAssist AI provides general wellness information and is not a substitute for professional medical advice.</p>
</div></body></html>"""


def _button(url: str, label: str) -> str:
    return (
        f'<p><a href="{url}" style="background:#0b5cab;color:#fff;padding:12px 20px;'
        f'border-radius:8px;text-decoration:none;display:inline-block">{label}</a></p>'
        f'<p style="font-size:12px;color:#6b7280">Or paste this link: {url}</p>'
    )


def send_verification_email(to: str, name: str, url: str, hours: int) -> bool:
    text = f"Hi {name},\n\nConfirm your email address: {url}\n\nThis link expires in {hours} hours."
    html = _wrap(
        "Confirm your email",
        f"<p>Hi {name},</p><p>Confirm your email address to finish setting up your account.</p>"
        f"{_button(url, 'Verify email')}<p>This link expires in {hours} hours.</p>",
    )
    return send_email(to, "Verify your HealthAssist AI email", text, html)


def send_password_reset_email(to: str, name: str, url: str, minutes: int) -> bool:
    text = (
        f"Hi {name},\n\nReset your password: {url}\n\nThis link expires in {minutes} minutes "
        "and can be used once. If you didn't ask for this, ignore this email."
    )
    html = _wrap(
        "Reset your password",
        f"<p>Hi {name},</p><p>We received a request to reset your password.</p>"
        f"{_button(url, 'Reset password')}<p>This link expires in {minutes} minutes and can be "
        "used once. If you didn't request this, you can ignore this email.</p>",
    )
    return send_email(to, "Reset your HealthAssist AI password", text, html)


def send_email_change_email(to: str, name: str, url: str, hours: int) -> bool:
    text = f"Hi {name},\n\nConfirm your new email address: {url}\n\nExpires in {hours} hours."
    html = _wrap(
        "Confirm your new email",
        f"<p>Hi {name},</p>{_button(url, 'Confirm new email')}<p>Expires in {hours} hours.</p>",
    )
    return send_email(to, "Confirm your new HealthAssist AI email", text, html)


def send_security_alert(to: str, name: str, what: str) -> bool:
    text = f"Hi {name},\n\n{what}\n\nIf this wasn't you, reset your password immediately."
    html = _wrap(
        "Security alert",
        f"<p>Hi {name},</p><p>{what}</p><p>If this wasn't you, reset your password immediately.</p>",
    )
    return send_email(to, "HealthAssist AI security alert", text, html)
