from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


REQUIRED_CAPABILITIES = (
    "postgres_http_runtime",
    "secure_http_boundary",
    "privacy_policy_url",
    "terms_url",
    "account_deletion_flow",
    "data_export_flow",
    "retention_policy",
    "photo_object_storage",
    "photo_moderation",
    "block_and_report",
    "push_provider_delivery",
    "billing_provider_verification",
    "apple_sign_in",
    "google_sign_in",
    "ios_build_pipeline",
    "android_build_pipeline",
    "store_metadata",
    "review_test_account",
)

BLOCKER_LABELS = {
    "postgres_http_runtime": "Новый PostgreSQL backend не подключён к публичному HTTP runtime.",
    "secure_http_boundary": "Security controls Phase 21 не применены end-to-end на публичном HTTP boundary.",
    "privacy_policy_url": "Нет опубликованного Privacy Policy URL.",
    "terms_url": "Нет опубликованных Terms of Use.",
    "account_deletion_flow": "Нет завершённого пользовательского account-deletion flow.",
    "data_export_flow": "Нет завершённого пользовательского data-export flow.",
    "retention_policy": "Не зафиксирована и не реализована retention policy.",
    "photo_object_storage": "Production object storage для фото не настроен.",
    "photo_moderation": "Photo moderation должна быть доступна в production console.",
    "block_and_report": "Block/report flows должны быть доступны из production client.",
    "push_provider_delivery": "Не подключена реальная APNS/FCM доставка.",
    "billing_provider_verification": "Не подключена production verification покупок/подписок.",
    "apple_sign_in": "Sign in with Apple не подключён в production client/backend.",
    "google_sign_in": "Google Sign-In не подключён в production client/backend.",
    "ios_build_pipeline": "Нет воспроизводимого iOS release build pipeline.",
    "android_build_pipeline": "Нет воспроизводимого Android release build pipeline.",
    "store_metadata": "Не подготовлен полный store listing/metadata package.",
    "review_test_account": "Не подготовлен review/test account и инструкции для ревью.",
}


@dataclass(frozen=True)
class StoreReadiness:
    ready: bool
    completed: tuple[str, ...]
    blockers: tuple[str, ...]
    blocker_details: tuple[str, ...]

    @property
    def completion_percent(self) -> int:
        total = len(REQUIRED_CAPABILITIES)
        return int(round(len(self.completed) * 100 / total)) if total else 100


def evaluate_store_readiness(capabilities: Mapping[str, bool]) -> StoreReadiness:
    completed = tuple(
        key for key in REQUIRED_CAPABILITIES if bool(capabilities.get(key, False))
    )
    blockers = tuple(key for key in REQUIRED_CAPABILITIES if key not in completed)
    return StoreReadiness(
        ready=not blockers,
        completed=completed,
        blockers=blockers,
        blocker_details=tuple(BLOCKER_LABELS[key] for key in blockers),
    )


def current_matchlab_readiness() -> StoreReadiness:
    # This snapshot is intentionally fail-closed. Only capabilities that are
    # demonstrably complete in the current repository architecture are true.
    return evaluate_store_readiness(
        {
            "postgres_http_runtime": False,
            "secure_http_boundary": False,
            "privacy_policy_url": False,
            "terms_url": False,
            "account_deletion_flow": False,
            "data_export_flow": False,
            "retention_policy": False,
            "photo_object_storage": False,
            "photo_moderation": True,
            "block_and_report": True,
            "push_provider_delivery": False,
            "billing_provider_verification": False,
            "apple_sign_in": False,
            "google_sign_in": False,
            "ios_build_pipeline": False,
            "android_build_pipeline": False,
            "store_metadata": False,
            "review_test_account": False,
        }
    )
