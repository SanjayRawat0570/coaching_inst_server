"""Outbound messaging — Resend email (free tier: 3000/month, 100/day).

Email is the only channel: WhatsApp needs a paid provider, so it was removed to
keep the project on free services only. Every sender fails soft and returns a
status dict so scheduled jobs never crash on a delivery error.
"""

import os


def send_email(to_email: str, subject: str, html: str) -> dict:
    """Send an email via Resend (free 3000/month)."""
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY")
        if not (resend.api_key and to_email):
            return {"ok": False, "channel": "email", "error": "missing config/email"}
        result = resend.Emails.send({
            "from": "Smart Coaching <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        return {"ok": True, "channel": "email", "id": result.get("id")}
    except Exception as e:
        return {"ok": False, "channel": "email", "error": str(e)}


def notify(to_email: str = None, subject: str = "", body: str = "") -> dict:
    """Email a plain-text body. Returns the delivery status."""
    if not to_email:
        return {"ok": False, "error": "no destination"}
    return send_email(to_email, subject or "Update from Smart Coaching", f"<p>{body}</p>")
