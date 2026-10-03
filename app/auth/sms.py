from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import phonenumbers


class SmsError(Exception):
    pass


def normalize_phone(value: str, *, default_region: str = "KZ") -> str:
    raw = (value or "").strip()
    try:
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else default_region)
    except phonenumbers.NumberParseException as exc:
        raise SmsError("invalid_phone_number") from exc

    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        raise SmsError("invalid_phone_number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


@dataclass(frozen=True)
class SmsSendResult:
    provider: str
    message_id: str | None


class SmsSender:
    def send_otp(self, *, phone_e164: str, code: str) -> SmsSendResult:
        raise NotImplementedError


class TwilioSmsSender(SmsSender):
    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str | None = None,
        messaging_service_sid: str | None = None,
    ):
        if not account_sid or not auth_token:
            raise SmsError("twilio_credentials_missing")
        if not from_number and not messaging_service_sid:
            raise SmsError("twilio_sender_missing")
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.messaging_service_sid = messaging_service_sid

    @classmethod
    def from_env(cls) -> "TwilioSmsSender":
        return cls(
            account_sid=os.environ.get("TWILIO_ACCOUNT_SID", "").strip(),
            auth_token=os.environ.get("TWILIO_AUTH_TOKEN", "").strip(),
            from_number=os.environ.get("TWILIO_FROM_NUMBER", "").strip() or None,
            messaging_service_sid=os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "").strip() or None,
        )

    def send_otp(self, *, phone_e164: str, code: str) -> SmsSendResult:
        form = {
            "To": phone_e164,
            "Body": f"MatchLab: код входа {code}. Никому не сообщайте этот код.",
        }
        if self.messaging_service_sid:
            form["MessagingServiceSid"] = self.messaging_service_sid
        else:
            form["From"] = self.from_number or ""

        raw = urllib.parse.urlencode(form).encode("utf-8")
        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            + urllib.parse.quote(self.account_sid, safe="")
            + "/Messages.json"
        )
        auth = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode("utf-8")
        ).decode("ascii")
        request = urllib.request.Request(
            url,
            data=raw,
            method="POST",
            headers={
                "Authorization": "Basic " + auth,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", errors="replace")
            raise SmsError(f"twilio_send_failed:{exc.code}:{detail}") from exc
        except Exception as exc:
            raise SmsError("twilio_send_failed") from exc

        return SmsSendResult(provider="TWILIO", message_id=payload.get("sid"))


def sms_sender_from_env() -> SmsSender:
    provider = os.environ.get("SMS_PROVIDER", "twilio").strip().lower()
    if provider == "twilio":
        return TwilioSmsSender.from_env()
    raise SmsError("unsupported_sms_provider")
