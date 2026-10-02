ALGORITHM_VERSION = "mutual-v1"

CATEGORY_SECTIONS = {
    "values_score": {"Ценности", "Деньги"},
    "relationship_score": {"Отношения", "Эмоциональная близость"},
    "family_score": {"Семья", "Дети"},
    "lifestyle_score": {"Образ жизни", "Привычки"},
    "communication_score": {"Конфликты", "Социальность"},
    "personality_score": {"Обо мне", "Характер", "Личное пространство"},
    "future_score": {"Работа и амбиции", "Жизненные планы"},
    "interests_score": {"Интересы"},
}

FINAL_WEIGHTS = {
    "compatibility": 0.60,
    "mutual_preferences": 0.25,
    "activity": 0.10,
    "readiness": 0.05,
}

SOFT_IMPORTANCE_WEIGHT = {
    "IMPORTANT": 2.0,
    "PREFERENCE": 1.0,
}
