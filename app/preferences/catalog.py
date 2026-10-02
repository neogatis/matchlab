from __future__ import annotations

PREFERENCE_IMPORTANCE = ("HARD", "IMPORTANT", "PREFERENCE", "IGNORE")

PREFERENCE_CATALOG = {
    "age": {
        "label": "Возраст",
        "kind": "range",
        "required": True,
        "minimum": 18,
        "maximum": 100,
    },
    "gender": {
        "label": "Пол",
        "kind": "multi",
        "required": True,
        "options": ("M", "F", "OTHER"),
    },
    "market": {
        "label": "Город",
        "kind": "multi_text",
        "required": True,
        "max_items": 20,
    },
    "distance_km": {
        "label": "Расстояние",
        "kind": "max",
        "required": True,
        "minimum": 1,
        "maximum": 1000,
    },
    "dating_goal": {
        "label": "Цель знакомства",
        "kind": "multi",
        "required": True,
        "options": ("SERIOUS", "FAMILY", "SEE", "CHAT", "UNKNOWN"),
    },
    "children_status": {
        "label": "Дети",
        "kind": "multi",
        "required": True,
        "options": ("NO_CHILDREN", "HAS_CHILDREN", "ANY"),
    },
    "children_plans": {
        "label": "Планы на детей",
        "kind": "multi",
        "required": True,
        "options": ("WANTS", "MAYBE", "DOES_NOT_WANT", "ANY"),
    },
    "smoking": {
        "label": "Курение",
        "kind": "multi",
        "required": True,
        "options": ("NO", "RARE", "YES", "ANY"),
    },
    "alcohol": {
        "label": "Алкоголь",
        "kind": "multi",
        "required": True,
        "options": ("NO", "RARE", "MODERATE", "YES", "ANY"),
    },
    "lifestyle": {
        "label": "Образ жизни",
        "kind": "multi",
        "required": True,
        "options": ("CALM", "BALANCED", "ACTIVE", "VERY_ACTIVE", "ANY"),
    },
    "height": {
        "label": "Рост",
        "kind": "range",
        "required": True,
        "minimum": 100,
        "maximum": 250,
    },
    "religion": {
        "label": "Религия",
        "kind": "multi_text",
        "required": False,
        "max_items": 20,
    },
    "nationality": {
        "label": "Национальность",
        "kind": "multi_text",
        "required": False,
        "max_items": 20,
        "self_reported_only": True,
    },
}

CORE_PREFERENCE_KEYS = tuple(
    key for key, spec in PREFERENCE_CATALOG.items() if spec.get("required")
)
