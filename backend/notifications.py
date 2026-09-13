"""Customer notification dispatcher.

WhatsApp/SMS/Email are stubbed — no provider (Twilio, WhatsApp Business
API, an SMTP relay, ...) is wired up yet, so `_send_*` just marks the
message "Sent" without actually transmitting it. The point of this module
right now is the trigger wiring and the audit trail (notification_logs),
not the transport: swap a `_send_*` body for a real provider call when one
is chosen, and every call site in server.py stays unchanged.

ponytail: stub transport, upgrade to a real provider client per channel
when credentials exist. Until then this is a notification LOG, not a
notification SENDER.
"""
from __future__ import annotations

import os

import requests

import models as m
import tenancy

# {event: message template}. `ref` and any extra kwargs passed to notify()
# fill the template — a template with no matching kwarg leaves the
# placeholder as literal text rather than raising, since a customer
# message is not the place for a KeyError.
EVENTS = {
    "quote_created": "Hi {customer_name}, your quotation {ref} has been created. We'll follow up shortly.",
    "order_confirmed": "Hi {customer_name}, your order {ref} is confirmed. Thank you!",
    "installation_scheduled": "Hi {customer_name}, installation for {ref} is scheduled around {date}.",
    "payment_cleared": "Hi {customer_name}, payment for {ref} is fully received. Balance is now zero.",
    "payment_reminder": "Hi {customer_name}, a friendly reminder that payment for {ref} is pending. Let us know if you have any questions.",
    "follow_up": "Hi {customer_name}, just following up on {ref}. Let us know how we can help.",
}

# Click-to-chat contexts (manual WhatsApp button on Leads/Quotes/JourneyDrawer)
# map to the same EVENTS templates an automated notify() would use, so the
# copy a customer sees never drifts between the two channels.
CLICK_TO_CHAT_EVENTS = {
    "quote-shared": "quote_created",
    "payment-reminder": "payment_reminder",
    "installation-scheduled": "installation_scheduled",
    "follow-up": "follow_up",
}


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _render(event: str, **fmt) -> str:
    template = EVENTS.get(event, event)
    return template.format_map(_SafeDict(fmt))


def _send_whatsapp(to: str, message: str) -> tuple[str, str]:
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        return ("Sent", "")  # unconfigured tenant: identical stub behavior
    try:
        resp = requests.post(
            f"https://graph.facebook.com/v20.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}},
            timeout=10,
        )
        if resp.status_code >= 400:
            return ("Failed", resp.text[:300])
        return ("Sent", "")
    except Exception as e:
        return ("Failed", str(e))


def _send_sms(to: str, message: str) -> tuple[str, str]:
    return ("Sent", "")


def _send_email(to: str, message: str) -> tuple[str, str]:
    return ("Sent", "")


_CHANNELS = {"whatsapp": _send_whatsapp, "sms": _send_sms, "email": _send_email}


async def notify(db, user: dict, event: str, *, to: str, customer_name: str = "",
                  ref_type: str = "", ref_id: str = "", channel: str = "whatsapp", **fmt) -> None:
    """Fire-and-log a customer notification. Never raises — same guarantee
    server.py's _audit() makes for the audit log: a notification failure
    must not roll back or block the business write that triggered it."""
    if not to:
        return
    message = _render(event, customer_name=customer_name, ref=ref_id, **fmt)
    send = _CHANNELS.get(channel, _send_whatsapp)
    try:
        status, error = send(to, message)
    except Exception as e:
        status, error = "Failed", str(e)
    doc = {
        "id": m.new_id(), "created_at": m.now_iso(), "event": event, "channel": channel,
        "to": to, "customer_name": customer_name, "ref_type": ref_type, "ref_id": ref_id,
        "message": message, "status": status, "error": error,
    }
    tenancy.stamp(doc, "notification_logs", user)
    try:
        await db.notification_logs.insert_one(doc)
    except Exception:
        pass


async def log_manual_click(db, user: dict, context: str, *, to: str, customer_name: str = "",
                            ref_type: str = "", ref_id: str = "") -> None:
    """Logs a click-to-chat WhatsApp button press — no transport call (the
    browser already opened wa.me directly), status "Sent (manual)" so this
    is distinguishable from an automated notify() send in the audit trail."""
    if not to:
        return
    event = CLICK_TO_CHAT_EVENTS.get(context, context)
    message = _render(event, customer_name=customer_name, ref=ref_id)
    doc = {
        "id": m.new_id(), "created_at": m.now_iso(), "event": event, "channel": "whatsapp",
        "to": to, "customer_name": customer_name, "ref_type": ref_type, "ref_id": ref_id,
        "message": message, "status": "Sent (manual)", "error": "",
    }
    tenancy.stamp(doc, "notification_logs", user)
    try:
        await db.notification_logs.insert_one(doc)
    except Exception:
        pass
