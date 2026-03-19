"""
Notification Service — automated customer ETA communications.

Supports:
  - SMS via Twilio (primary)
  - Email via SMTP / SendGrid
  - Webhook (for custom integrations)

Messages are rendered from configurable templates with dynamic ETA data.
All sends are logged and rate-limited (max 1 ETA per customer per 30 min).
"""

from __future__ import annotations
import logging
import os
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from typing import Any, Dict, Optional, Set

import httpx

logger = logging.getLogger(__name__)


# ─── Message Templates ────────────────────────────────────────────────────────

SMS_ETA_TEMPLATE = Template(
    "Hi $customer_name! Your $job_type tech $tech_name is on the way. "
    "ETA: $eta_time ($travel_minutes min away). "
    "Track: $map_link | Reply STOP to opt out."
)

SMS_ETA_UPDATE_TEMPLATE = Template(
    "Update for $customer_name: $tech_name's ETA has changed to $new_eta_time "
    "(was $old_eta_time). We apologize for any inconvenience."
)

SMS_ARRIVAL_TEMPLATE = Template(
    "Hi $customer_name! $tech_name has arrived at your location. "
    "Your $job_type service is starting now."
)

SMS_COMPLETED_TEMPLATE = Template(
    "Hi $customer_name! Your $job_type service is complete. "
    "Thanks for choosing us! Please rate your experience: $rating_link"
)

EMAIL_ETA_SUBJECT = "Your Technician Is On The Way — ETA $eta_time"

EMAIL_ETA_BODY_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="background: #1a73e8; padding: 20px; border-radius: 8px 8px 0 0;">
    <h1 style="color: white; margin: 0; font-size: 22px;">Your Technician Is On The Way</h1>
  </div>
  <div style="background: #f8f9fa; padding: 24px; border-radius: 0 0 8px 8px;">
    <p style="font-size: 16px;">Hi <strong>$customer_name</strong>,</p>
    <p>Good news! <strong>$tech_name</strong> is heading to your location now.</p>

    <div style="background: white; border-left: 4px solid #1a73e8; padding: 16px; margin: 20px 0; border-radius: 4px;">
      <p style="margin: 4px 0;"><strong>🕐 Estimated Arrival:</strong> $eta_time</p>
      <p style="margin: 4px 0;"><strong>🚗 Travel Time:</strong> ~$travel_minutes minutes</p>
      <p style="margin: 4px 0;"><strong>🔧 Service:</strong> $job_type</p>
      <p style="margin: 4px 0;"><strong>📍 Your Address:</strong> $customer_address</p>
    </div>

    <div style="text-align: center; margin: 24px 0;">
      <a href="$google_map_link" style="background: #1a73e8; color: white; padding: 12px 24px;
         border-radius: 6px; text-decoration: none; margin: 0 8px; display: inline-block;">
        📍 Track on Google Maps
      </a>
      <a href="$apple_map_link" style="background: #333; color: white; padding: 12px 24px;
         border-radius: 6px; text-decoration: none; margin: 0 8px; display: inline-block;">
        🗺 Open in Apple Maps
      </a>
    </div>

    <p style="color: #666; font-size: 13px; margin-top: 24px;">
      Questions? Call us or reply to this email.<br>
      You're receiving this because you scheduled a service call.
    </p>
  </div>
</body>
</html>
"""


def _format_eta_time(eta: datetime, tz_offset_hours: int = 0) -> str:
    """Format ETA as human-readable time string."""
    # Add timezone offset for local display
    local_eta = eta + timedelta(hours=tz_offset_hours)
    return local_eta.strftime("%I:%M %p").lstrip("0")


def _format_job_type(job_type: str) -> str:
    """Convert snake_case job type to human-readable."""
    return job_type.replace("_", " ").title()


class NotificationService:
    """
    Unified customer notification service with SMS, email, and webhook support.
    Automatically rate-limits to avoid spamming customers.
    """

    RATE_LIMIT_SECONDS = 1800   # 30 minutes between ETA messages to same customer

    def __init__(
        self,
        # Twilio
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
        twilio_from_number: Optional[str] = None,
        # Email
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        email_from: Optional[str] = None,
        email_from_name: str = "Dispatch Team",
        # SendGrid (alternative to SMTP)
        sendgrid_api_key: Optional[str] = None,
        # Company info for messages
        company_name: str = "Your Service Company",
        company_phone: str = "",
        rating_base_url: str = "",
        # Webhook
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        # Twilio
        self.twilio_sid = twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token = twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = twilio_from_number or os.getenv("TWILIO_FROM_NUMBER", "")

        # Email
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user or os.getenv("SMTP_USER", "")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD", "")
        self.email_from = email_from or os.getenv("EMAIL_FROM", self.smtp_user)
        self.email_from_name = email_from_name
        self.sendgrid_api_key = sendgrid_api_key or os.getenv("SENDGRID_API_KEY", "")

        self.company_name = company_name or os.getenv("COMPANY_NAME", "Your Service Company")
        self.company_phone = company_phone or os.getenv("COMPANY_PHONE", "")
        self.rating_base_url = rating_base_url or os.getenv("RATING_BASE_URL", "")

        self.webhook_url = webhook_url or os.getenv("NOTIFICATION_WEBHOOK_URL", "")
        self.webhook_secret = webhook_secret or os.getenv("NOTIFICATION_WEBHOOK_SECRET", "")

        # Rate limiting: customer_id → last_notified_timestamp
        self._last_notified: Dict[str, float] = {}

    def _is_rate_limited(self, customer_id: str) -> bool:
        last = self._last_notified.get(customer_id, 0)
        return (time.time() - last) < self.RATE_LIMIT_SECONDS

    def _mark_notified(self, customer_id: str):
        self._last_notified[customer_id] = time.time()

    # ─── Primary API ──────────────────────────────────────────────────────────

    async def send_eta(
        self,
        job: Any,
        tech: Any,
        eta: datetime,
        travel_time_minutes: float,
    ) -> str:
        """
        Send initial ETA notification to customer (SMS + Email).
        Returns the message text that was sent.
        """
        customer = job.customer

        if self._is_rate_limited(customer.customer_id):
            logger.debug(f"Rate limit: skipping ETA for customer {customer.customer_id}")
            return ""

        eta_str = _format_eta_time(eta)
        job_type_str = _format_job_type(job.job_type.value)
        travel_str = str(int(travel_time_minutes))

        # Google/Apple map links
        google_link = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&destination={customer.latitude},{customer.longitude}&travelmode=driving"
        )
        apple_link = f"maps://?daddr={customer.latitude},{customer.longitude}&dirflg=d"

        sms_text = SMS_ETA_TEMPLATE.substitute(
            customer_name=customer.name.split()[0],
            job_type=job_type_str,
            tech_name=tech.name.split()[0],
            eta_time=eta_str,
            travel_minutes=travel_str,
            map_link=google_link,
        )

        message_sent = ""

        # Send SMS
        if customer.sms_opt_in and self.twilio_sid and self.twilio_token:
            sms_sent = await self._send_sms(customer.phone, sms_text)
            if sms_sent:
                message_sent = sms_text
                logger.info(f"ETA SMS sent to {customer.name} ({customer.phone}): ETA {eta_str}")

        # Send Email
        if customer.email_opt_in and self.email_from:
            email_body = Template(EMAIL_ETA_BODY_HTML).safe_substitute(
                customer_name=customer.name,
                tech_name=tech.name,
                eta_time=eta_str,
                travel_minutes=travel_str,
                job_type=job_type_str,
                customer_address=customer.address,
                google_map_link=google_link,
                apple_map_link=apple_link,
            )
            subject = Template(EMAIL_ETA_SUBJECT).safe_substitute(eta_time=eta_str)
            await self._send_email(
                to_addr=customer.email,
                to_name=customer.name,
                subject=subject,
                html_body=email_body,
            )

        # Fire webhook
        if self.webhook_url:
            await self._fire_webhook({
                "event": "eta_sent",
                "job_id": job.job_id,
                "customer_id": customer.customer_id,
                "tech_id": tech.tech_id,
                "eta": eta.isoformat(),
                "travel_minutes": travel_time_minutes,
            })

        self._mark_notified(customer.customer_id)
        return message_sent or sms_text  # Return text even if not sent (for logging)

    async def send_eta_update(
        self,
        job: Any,
        tech: Any,
        new_eta: datetime,
        old_eta: datetime,
    ) -> str:
        """Send an ETA change notification."""
        customer = job.customer
        new_str = _format_eta_time(new_eta)
        old_str = _format_eta_time(old_eta)

        sms_text = SMS_ETA_UPDATE_TEMPLATE.substitute(
            customer_name=customer.name.split()[0],
            tech_name=tech.name.split()[0],
            new_eta_time=new_str,
            old_eta_time=old_str,
        )

        if customer.sms_opt_in and self.twilio_sid:
            await self._send_sms(customer.phone, sms_text)
            logger.info(f"ETA update sent to {customer.name}: {old_str} → {new_str}")

        return sms_text

    async def send_arrival(self, job: Any, tech: Any) -> str:
        """Notify customer that tech has arrived."""
        customer = job.customer
        job_type_str = _format_job_type(job.job_type.value)

        text = SMS_ARRIVAL_TEMPLATE.substitute(
            customer_name=customer.name.split()[0],
            tech_name=tech.name.split()[0],
            job_type=job_type_str,
        )

        if customer.sms_opt_in and self.twilio_sid:
            await self._send_sms(customer.phone, text)
        return text

    async def send_completion(self, job: Any, tech: Any) -> str:
        """Send job completion notification with rating link."""
        customer = job.customer
        job_type_str = _format_job_type(job.job_type.value)
        rating_link = f"{self.rating_base_url}/rate/{job.job_id}" if self.rating_base_url else ""

        text = SMS_COMPLETED_TEMPLATE.substitute(
            customer_name=customer.name.split()[0],
            job_type=job_type_str,
            rating_link=rating_link or "us on Google",
        )

        if customer.sms_opt_in and self.twilio_sid:
            await self._send_sms(customer.phone, text)
        return text

    # ─── Twilio SMS ───────────────────────────────────────────────────────────

    async def _send_sms(self, to_number: str, body: str) -> bool:
        """Send SMS via Twilio REST API."""
        if not (self.twilio_sid and self.twilio_token and self.twilio_from):
            logger.debug("Twilio credentials not configured. SMS skipped.")
            return False

        clean_number = to_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not clean_number.startswith("+"):
            clean_number = "+1" + clean_number  # Default to US country code

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    url,
                    auth=(self.twilio_sid, self.twilio_token),
                    data={
                        "From": self.twilio_from,
                        "To": clean_number,
                        "Body": body[:1600],  # Twilio SMS limit
                    },
                    timeout=10.0,
                )
                if r.status_code in (200, 201):
                    return True
                else:
                    logger.error(f"Twilio SMS failed: {r.status_code} {r.text[:200]}")
                    return False
        except Exception as e:
            logger.error(f"SMS send error: {e}")
            return False

    # ─── Email ────────────────────────────────────────────────────────────────

    async def _send_email(
        self,
        to_addr: str,
        to_name: str,
        subject: str,
        html_body: str,
        plain_body: Optional[str] = None,
    ) -> bool:
        """Send email via SendGrid API or SMTP fallback."""
        if self.sendgrid_api_key:
            return await self._send_via_sendgrid(to_addr, to_name, subject, html_body)
        elif self.smtp_host and self.smtp_user:
            return await self._send_via_smtp(to_addr, to_name, subject, html_body, plain_body)
        else:
            logger.debug("No email provider configured. Email skipped.")
            return False

    async def _send_via_sendgrid(
        self, to_addr: str, to_name: str, subject: str, html_body: str
    ) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": to_addr, "name": to_name}]}],
                        "from": {"email": self.email_from, "name": self.email_from_name},
                        "subject": subject,
                        "content": [{"type": "text/html", "value": html_body}],
                    },
                    timeout=10.0,
                )
                return r.status_code in (200, 202)
        except Exception as e:
            logger.error(f"SendGrid email failed: {e}")
            return False

    async def _send_via_smtp(
        self, to_addr: str, to_name: str, subject: str, html_body: str,
        plain_body: Optional[str] = None
    ) -> bool:
        import asyncio

        def _send():
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.email_from_name} <{self.email_from}>"
            msg["To"] = f"{to_name} <{to_addr}>"
            if plain_body:
                msg.attach(MIMEText(plain_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, to_addr, msg.as_string())
            return True

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _send)
        except Exception as e:
            logger.error(f"SMTP email failed: {e}")
            return False

    # ─── Webhook ──────────────────────────────────────────────────────────────

    async def _fire_webhook(self, payload: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False
        try:
            async with httpx.AsyncClient() as client:
                headers: Dict[str, str] = {"Content-Type": "application/json"}
                if self.webhook_secret:
                    import hmac, hashlib, json
                    body = json.dumps(payload).encode()
                    sig = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
                    headers["X-Dispatch-Signature"] = f"sha256={sig}"
                r = await client.post(self.webhook_url, json=payload, headers=headers, timeout=5.0)
                return r.status_code < 300
        except Exception as e:
            logger.debug(f"Webhook failed: {e}")
            return False
