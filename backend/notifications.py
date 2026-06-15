"""Outbound messaging — Twilio WhatsApp (primary) + Resend email (backup).

Both free-tier. Every sender fails soft and returns a status dict so scheduled jobs
never crash on a delivery error.
"""

import os


def send_whatsapp(to_phone: str, body: str) -> dict:
    """Send a WhatsApp message via the Twilio sandbox. to_phone e.g. '+9198...'."""
    try:
        from twilio.rest import Client
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        from_whatsapp = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        if not (sid and token and to_phone):
            return {"ok": False, "channel": "whatsapp", "error": "missing config/phone"}

        client = Client(sid, token)
        to = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
        msg = client.messages.create(body=body, from_=from_whatsapp, to=to)
        return {"ok": True, "channel": "whatsapp", "sid": msg.sid}
    except Exception as e:
        return {"ok": False, "channel": "whatsapp", "error": str(e)}


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


def notify(to_phone: str = None, to_email: str = None,
           subject: str = "", body: str = "") -> dict:
    """Try WhatsApp first, fall back to email. Returns the first successful result."""
    if to_phone:
        wa = send_whatsapp(to_phone, body)
        if wa["ok"]:
            return wa
    if to_email:
        return send_email(to_email, subject or "Update from Smart Coaching",
                          f"<p>{body}</p>")
    return {"ok": False, "error": "no destination"}
