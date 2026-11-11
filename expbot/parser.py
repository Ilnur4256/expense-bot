"""Разбор сообщений вида «500 еда обед», «такси 250», «1.5к продукты», «+50000 зарплата»."""

import re
from dataclasses import dataclass

CATEGORIES = {
    "Еда": ["еда", "обед", "ужин", "завтрак", "кафе", "ресторан", "кофе", "шаурма", "фастфуд"],
    "Продукты": ["продукты", "магазин", "супермаркет", "рынок", "базар", "globus", "глобус"],
    "Транспорт": ["такси", "автобус", "маршрутка", "бензин", "топливо", "проезд", "яндекс"],
    "Дом": ["аренда", "квартира", "свет", "вода", "газ", "коммуналка", "интернет", "ремонт"],
    "Связь": ["телефон", "мобильный", "баланс", "связь", "megacom", "o!", "beeline"],
    "Здоровье": ["аптека", "лекарства", "врач", "больница", "анализы", "стоматолог"],
    "Развлечения": ["кино", "игры", "подписка", "spotify", "netflix", "бар", "концерт"],
    "Одежда": ["одежда", "обувь", "куртка", "джинсы", "кроссовки"],
    "Доход": ["зарплата", "зп", "доход", "фриланс", "премия", "перевод"],
}
OTHER = "Другое"
AMOUNT_RE = re.compile(r"^(?P<sign>[+-])?(?P<num>\d+(?:[.,]\d+)?)\s*(?P<k>[кkк])?$", re.IGNORECASE)


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    amount: float  # всегда > 0; доход отмечается флагом is_income
    category: str
    comment: str
    is_income: bool = False


def parse_amount(token: str) -> tuple[float, bool] | None:
    m = AMOUNT_RE.match(token.replace(" ", ""))
    if not m:
        return None
    value = float(m["num"].replace(",", "."))
    if m["k"]:
        value *= 1000
    return round(value, 2), m["sign"] == "+"


def detect_category(words: list[str]) -> str:
    lowered = [w.lower() for w in words]
    for category, keywords in CATEGORIES.items():
        if category.lower() in lowered:
            return category
        for w in lowered:
            for k in keywords:
                # «продуктов» → «продукты», «аптеке» → «аптека»: сравниваем начало слова
                if w.startswith(k) or (len(w) >= 4 and k.startswith(w[:4]) and w[:4] == k[:4]):
                    return category
    return OTHER


def parse_message(text: str) -> Entry:
    tokens = text.strip().split()
    if not tokens:
        raise ParseError("Пустое сообщение")
    amount_info, rest = None, []
    for token in tokens:
        if amount_info is None and (parsed := parse_amount(token)):
            amount_info = parsed
        else:
            rest.append(token)
    if amount_info is None:
        raise ParseError("Не нашёл сумму. Пример: «450 обед» или «такси 250»")
    amount, plus = amount_info
    if amount <= 0:
        raise ParseError("Сумма должна быть больше нуля")
    if amount > 10_000_000:
        raise ParseError("Слишком большая сумма — проверьте, нет ли опечатки")
    category = detect_category(rest)
    is_income = plus or category == "Доход"
    return Entry(
        amount=amount,
        category="Доход" if is_income else category,
        comment=" ".join(rest),
        is_income=is_income,
    )
