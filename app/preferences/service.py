from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.profile.service import recompute_profile_completion
from app.analytics.events import EVENT_PARTNER_PREFERENCES_COMPLETED, track_once
from app.db.models import Market, PartnerPreference, Profile
from .catalog import CORE_PREFERENCE_KEYS, PREFERENCE_CATALOG, PREFERENCE_IMPORTANCE


class PreferenceError(Exception):
    pass


class UnknownPreference(PreferenceError):
    pass


class InvalidPreference(PreferenceError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe(values: list[Any]) -> list[Any]:
    out = []
    seen = set()
    for value in values:
        marker = str(value)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(value)
    return out


def _validate_importance(importance: str) -> str:
    value = (importance or "").upper()
    if value not in PREFERENCE_IMPORTANCE:
        raise InvalidPreference("Invalid preference importance")
    return value


def _validate_range(spec: dict, payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise InvalidPreference("Range preference must be an object")
    minimum = payload.get("min")
    maximum = payload.get("max")
    if isinstance(minimum, bool) or isinstance(maximum, bool):
        raise InvalidPreference("Range bounds must be numeric")
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        raise InvalidPreference("Range requires min and max")
    allowed_min = spec["minimum"]
    allowed_max = spec["maximum"]
    if minimum < allowed_min or maximum > allowed_max or minimum > maximum:
        raise InvalidPreference("Range is outside allowed bounds")
    return {"min": minimum, "max": maximum}


def _validate_max(spec: dict, payload: Any) -> dict:
    if isinstance(payload, dict):
        maximum = payload.get("max")
    else:
        maximum = payload
    if isinstance(maximum, bool) or not isinstance(maximum, (int, float)):
        raise InvalidPreference("Maximum value must be numeric")
    if maximum < spec["minimum"] or maximum > spec["maximum"]:
        raise InvalidPreference("Maximum value is outside allowed bounds")
    return {"max": maximum}


def _validate_multi(spec: dict, payload: Any) -> list[str]:
    if not isinstance(payload, list) or not payload:
        raise InvalidPreference("Preference must contain at least one option")
    values = _dedupe([str(v).strip() for v in payload if str(v).strip()])
    allowed = set(spec["options"])
    if not values or any(v not in allowed for v in values):
        raise InvalidPreference("Preference contains an unsupported option")
    if "ANY" in values and len(values) > 1:
        raise InvalidPreference("ANY cannot be combined with other options")
    return values


def _validate_multi_text(spec: dict, payload: Any) -> list[str]:
    if not isinstance(payload, list) or not payload:
        raise InvalidPreference("Preference must contain at least one value")
    values = _dedupe([str(v).strip() for v in payload if str(v).strip()])
    if not values:
        raise InvalidPreference("Preference must contain at least one value")
    if len(values) > int(spec.get("max_items", 20)):
        raise InvalidPreference("Too many preference values")
    if any(len(v) > 120 for v in values):
        raise InvalidPreference("Preference value is too long")
    return values


def _validate_payload(db: Session, key: str, payload: Any) -> dict[str, Any]:
    spec = PREFERENCE_CATALOG[key]
    kind = spec["kind"]
    if kind == "range":
        return _validate_range(spec, payload)
    if kind == "max":
        return _validate_max(spec, payload)
    if kind == "multi":
        return {"values": _validate_multi(spec, payload)}
    if kind == "multi_text":
        values = _validate_multi_text(spec, payload)
        if key == "market":
            configured = set(
                db.execute(select(Market.code).where(Market.registration_open.is_(True))).scalars()
            )
            if any(v not in configured for v in values):
                raise InvalidPreference("Unknown or closed market")
        return {"values": values}
    raise InvalidPreference("Unsupported preference kind")


def set_preference(
    db: Session,
    *,
    user_id: int,
    key: str,
    importance: str,
    value: Any = None,
    now: datetime | None = None,
) -> PartnerPreference:
    now = now or utcnow()
    if key not in PREFERENCE_CATALOG:
        raise UnknownPreference(key)

    profile = db.get(Profile, user_id)
    if profile is None:
        raise PreferenceError("Profile not found")

    importance = _validate_importance(importance)

    # Backward-compatible normalization for old web clients that encoded
    # "Не важно" as a real value such as ["ANY"]. IGNORE must mean that
    # the criterion takes no part in filtering or scoring.
    if (
        importance != "IGNORE"
        and isinstance(value, list)
        and len(value) == 1
        and str(value[0]).upper() == "ANY"
    ):
        importance = "IGNORE"
        value = None

    normalized: dict[str, Any] = {}
    if importance != "IGNORE":
        normalized = _validate_payload(db, key, value)

    row = db.execute(
        select(PartnerPreference).where(
            PartnerPreference.user_id == user_id,
            PartnerPreference.criterion_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        row = PartnerPreference(user_id=user_id, criterion_key=key)
        db.add(row)

    row.importance = importance
    row.value_text = None
    row.value_bool = None
    row.min_value = None
    row.max_value = None
    row.values_json = None

    if "min" in normalized:
        row.min_value = normalized["min"]
    if "max" in normalized:
        row.max_value = normalized["max"]
    if "values" in normalized:
        row.values_json = normalized["values"]

    row.updated_at = now
    db.flush()
    recompute_completion(db, user_id=user_id)
    return row


def set_preferences(
    db: Session,
    *,
    user_id: int,
    preferences: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(preferences, dict):
        raise InvalidPreference("Preferences must be an object")
    for key, config in preferences.items():
        if not isinstance(config, dict):
            raise InvalidPreference("Preference configuration must be an object")
        set_preference(
            db,
            user_id=user_id,
            key=key,
            importance=config.get("importance", ""),
            value=config.get("value"),
        )
    return completion(db, user_id=user_id)


def completion(db: Session, *, user_id: int) -> dict[str, Any]:
    configured = set(
        db.execute(
            select(PartnerPreference.criterion_key).where(PartnerPreference.user_id == user_id)
        ).scalars()
    )
    missing = [key for key in CORE_PREFERENCE_KEYS if key not in configured]
    complete = not missing
    return {
        "required_total": len(CORE_PREFERENCE_KEYS),
        "configured_required": len(CORE_PREFERENCE_KEYS) - len(missing),
        "missing": missing,
        "percent": int(round((len(CORE_PREFERENCE_KEYS) - len(missing)) * 100 / len(CORE_PREFERENCE_KEYS))),
        "complete": complete,
    }


def recompute_completion(db: Session, *, user_id: int) -> bool:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise PreferenceError("Profile not found")
    state = completion(db, user_id=user_id)
    profile.partner_preferences_completed = bool(state["complete"])
    profile.updated_at = utcnow()
    db.flush()
    if profile.partner_preferences_completed:
        track_once(
            db,
            event_type=EVENT_PARTNER_PREFERENCES_COMPLETED,
            user_id=user_id,
            metadata={"configured_required": state["configured_required"]},
        )
    recompute_profile_completion(db, user_id=user_id)
    return profile.partner_preferences_completed


def get_preferences(db: Session, *, user_id: int) -> dict[str, dict[str, Any]]:
    rows = db.execute(
        select(PartnerPreference)
        .where(PartnerPreference.user_id == user_id)
        .order_by(PartnerPreference.criterion_key)
    ).scalars()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        value: Any = None
        if row.values_json is not None:
            value = row.values_json
        elif row.min_value is not None or row.max_value is not None:
            value = {
                "min": float(row.min_value) if isinstance(row.min_value, Decimal) else row.min_value,
                "max": float(row.max_value) if isinstance(row.max_value, Decimal) else row.max_value,
            }
            if value["min"] is None:
                value.pop("min")
        elif row.value_text is not None:
            value = row.value_text
        elif row.value_bool is not None:
            value = row.value_bool
        out[row.criterion_key] = {
            "importance": row.importance,
            "value": value,
            "updated_at": row.updated_at,
        }
    return out
