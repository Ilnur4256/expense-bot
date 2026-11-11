"""Статистика и проверка бюджета — чистые функции, удобно тестировать."""

from collections import defaultdict
from datetime import date

from expbot.storage import Saved

BAR_WIDTH = 10


def money(x: float) -> str:
    return (
        f"{x:,.0f}".replace(",", " ") + " сом"
        if x == int(x)
        else f"{x:,.2f}".replace(",", " ") + " сом"
    )


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, date.fromordinal(next_month.toordinal() - 1)


def summary(entries: list[Saved], title: str) -> str:
    expenses = [s.entry for s in entries if not s.entry.is_income]
    income = sum(s.entry.amount for s in entries if s.entry.is_income)
    total = sum(e.amount for e in expenses)
    if not entries:
        return f"{title}\nЗаписей нет."
    by_cat: dict[str, float] = defaultdict(float)
    for e in expenses:
        by_cat[e.category] += e.amount
    lines = [f"📊 {title}", f"Расходы: {money(total)}"]
    if income:
        lines.append(f"Доходы: {money(income)} · баланс: {money(income - total)}")
    for cat, amount in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
        share = amount / total if total else 0
        bar = "█" * max(1, round(share * BAR_WIDTH))
        lines.append(f"{bar} {cat}: {money(amount)} ({share:.0%})")
    return "\n".join(lines)


def budget_warning(spent_before: float, spent_now: float, budget: float | None) -> str | None:
    """Предупреждаем один раз при пересечении 80% и 100% месячного бюджета."""
    if not budget:
        return None
    for threshold, text in ((1.0, "🚨 Бюджет на месяц превышен"), (0.8, "⚠️ Потрачено 80% бюджета")):
        if spent_before < budget * threshold <= spent_now:
            return f"{text}: {money(spent_now)} из {money(budget)}"
    return None
