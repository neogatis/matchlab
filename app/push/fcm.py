from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from app.push.service import PushProviderError, PushSendResult


FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def _env_value(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


@dataclass
class FcmProviderClient:
    project_id: str
    credentials: Any
    timeout_seconds: int = 10

    @classmethod
    def from_env(cls) -> "FcmProviderClient":
        raw = _env_value("FIREBASE_SERVICE_ACCOUNT_JSON")
        if not raw:
            raise PushProviderError("firebase_service_account_missing")
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PushProviderError("firebase_service_account_invalid_json") from exc

        project_id = _env_value("FIREBASE_PROJECT_ID") or str(info.get("project_id") or "").strip()
        if not project_id:
            raise PushProviderError("firebase_project_id_missing")

        try:
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=[FCM_SCOPE],
            )
        except Exception as exc:
            raise PushProviderError("firebase_service_account_invalid") from exc
        return cls(project_id=project_id, credentials=credentials)

    def _access_token(self) -> str:
        if not self.credentials.valid or not self.credentials.token:
            self.credentials.refresh(GoogleAuthRequest())
        token = str(self.credentials.token or "")
        if not token:
            raise PushProviderError("firebase_access_token_missing")
        return token

    @staticmethod
    def _provider_error_code(payload: dict[str, Any]) -> str | None:
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        details = error.get("details")
        if not isinstance(details, list):
            return None
        for item in details:
            if not isinstance(item, dict):
                continue
            code = item.get("errorCode")
            if isinstance(code, str) and code:
                return code
        return None

    def send(
        self,
        *,
        token: str,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> PushSendResult:
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        payload = {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "data": {str(k): str(v) for k, v in data.items()},
                "android": {
                    "priority": "high",
                },
            }
        }
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": "Bearer " + self._access_token(),
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            return PushSendResult(ok=False, error=type(exc).__name__)

        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {}

        if response.status_code == 200:
            return PushSendResult(
                ok=True,
                provider_message_id=str(response_payload.get("name") or "") or None,
            )

        provider_code = self._provider_error_code(response_payload)
        invalid_token = provider_code == "UNREGISTERED"

        error = response_payload.get("error")
        if isinstance(error, dict):
            status = str(error.get("status") or "")
            message = str(error.get("message") or "")
            error_text = ":".join(
                part for part in [provider_code or status, message[:400]] if part
            )
        else:
            error_text = provider_code or f"http_{response.status_code}"

        return PushSendResult(
            ok=False,
            invalid_token=invalid_token,
            error=(error_text or f"http_{response.status_code}")[:1000],
        )
