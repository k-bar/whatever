"""Outgoing mail: account verification and password reset.

The boxes send through Amazon SES (sesv2 SendEmail, as syrenka.me: infra/stacks/mail_stack.py) with
their instance role. Locally (mail_backend "log") nothing is sent: the mail is logged and appended to
`outbox`, which the tests read.
"""

import logging
from dataclasses import dataclass
from html import escape

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    html: str


outbox: list[Mail] = []


def send(mail: Mail) -> None:
    if settings.mail_backend != "ses":
        log.warning(
            "mail (not sent, backend=%s) to %s: %s\n%s",
            settings.mail_backend,
            mail.to,
            mail.subject,
            mail.text,
        )
        outbox.append(mail)
        return
    import boto3  # only needed where mail is really sent

    try:
        boto3.client("sesv2", region_name=settings.ses_region).send_email(
            FromEmailAddress=settings.mail_from,
            Destination={"ToAddresses": [mail.to]},
            Content={
                "Simple": {
                    "Subject": {"Data": mail.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": mail.text, "Charset": "UTF-8"},
                        "Html": {"Data": mail.html, "Charset": "UTF-8"},
                    },
                }
            },
        )
    except Exception:  # runs as a background task: log it, the user can ask for another mail
        log.exception("SES could not send %r to %s", mail.subject, mail.to)


def _layout(greeting: str, lines: list[str], button: str, link: str, footer: str) -> str:
    paras = "".join(f'<p style="margin:0 0 14px">{escape(line)}</p>' for line in lines)
    return f"""<!doctype html><html><body style="margin:0;background:#f4f1ec;font-family:system-ui,sans-serif;color:#1d1b19">
<div style="max-width:480px;margin:32px auto;background:#fff;border-radius:18px;padding:28px 28px 22px">
<div style="font-weight:700;font-size:20px;margin-bottom:18px">Syrenka</div>
<p style="margin:0 0 14px">{escape(greeting)}</p>{paras}
<p style="margin:22px 0"><a href="{escape(link)}" style="background:#1d1b19;color:#fff;text-decoration:none;padding:12px 20px;border-radius:999px;display:inline-block">{escape(button)}</a></p>
<p style="margin:0;font-size:13px;color:#6b665f">{escape(footer)}</p>
<p style="margin:10px 0 0;font-size:12px;color:#9a948b;word-break:break-all">{escape(link)}</p>
</div></body></html>"""


def verification_mail(to: str, name: str, link: str) -> Mail:
    hours = settings.verify_token_hours
    lines = [
        "Welcome to Syrenka, everything happening in Warsaw on one map.",
        "Confirm this is your email address to add friends, create events and join event chats.",
    ]
    footer = f"The link works for {hours} hours. If you didn't sign up, ignore this mail."
    text = f"Hi {name},\n\n" + "\n".join(lines) + f"\n\nConfirm your email: {link}\n\n{footer}\n"
    return Mail(
        to,
        "Confirm your email for Syrenka",
        text,
        _layout(f"Hi {name},", lines, "Confirm email", link, footer),
    )


def reset_mail(to: str, name: str, link: str) -> Mail:
    minutes = settings.reset_token_minutes
    lines = ["Someone (hopefully you) asked to reset the password of your Syrenka account."]
    footer = f"The link works for {minutes} minutes and only once. If it wasn't you, ignore this mail: your password stays the same."
    text = f"Hi {name},\n\n" + "\n".join(lines) + f"\n\nChoose a new password: {link}\n\n{footer}\n"
    return Mail(
        to,
        "Reset your Syrenka password",
        text,
        _layout(f"Hi {name},", lines, "Choose a new password", link, footer),
    )
