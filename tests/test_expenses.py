from datetime import date, datetime

import pytest

from expbot import stats
from expbot.parser import Entry, ParseError, parse_message
from expbot.sheets import SheetsMirror
from expbot.storage import Storage


@pytest.mark.parametrize(
    "text, amount, category, income",
    [
        ("500 еда обед", 500, "Еда", False),
        ("такси 250", 250, "Транспорт", False),
        ("1.5к продукты", 1500, "Продукты", False),
        ("Аптека 320,50", 320.5, "Здоровье", False),
        ("+50000 зарплата", 50000, "Доход", True),
        ("зп 45k", 45000, "Доход", True),
        ("300 что-то странное", 300, "Другое", False),
        ("1200 продуктов на неделю", 1200, "Продукты", False),
    ],
)
def test_parse(text, amount, category, income):
    e = parse_message(text)
    assert (e.amount, e.category, e.is_income) == (amount, category, income)


@pytest.mark.parametrize("text", ["", "обед", "0 обед", "99999999 обед"])
def test_parse_errors(text):
    with pytest.raises(ParseError):
        parse_message(text)


@pytest.fixture
def storage(tmp_path):
    return Storage(str(tmp_path / "e.db"))


def test_storage_period_undo_and_isolation(storage):
    storage.add(1, Entry(100, "Еда", "обед"), datetime(2026, 11, 1, 12))
    storage.add(1, Entry(200, "Транспорт", "такси"), datetime(2026, 11, 2, 9))
    storage.add(2, Entry(999, "Еда", "чужое"), datetime(2026, 11, 2, 9))
    assert [s.entry.amount for s in storage.between(1, date(2026, 11, 2), date(2026, 11, 2))] == [
        200
    ]
    assert len(storage.between(1, date(2026, 11, 1), date(2026, 11, 30))) == 2
    removed = storage.undo_last(1)
    assert removed.entry.amount == 200
    assert len(storage.between(1, date(2026, 11, 1), date(2026, 11, 30))) == 1
    assert storage.undo_last(3) is None


def test_budget_and_export(storage):
    assert storage.get_budget(1) is None
    storage.set_budget(1, 30000)
    storage.set_budget(1, 25000)
    assert storage.get_budget(1) == 25000
    storage.add(1, Entry(100, "Еда", "обед, кафе"), datetime(2026, 11, 1, 12, 30))
    csv_text = storage.export_csv(1).decode("utf-8-sig").splitlines()
    assert csv_text[0] == "Дата,Сумма,Категория,Комментарий,Тип"
    assert csv_text[1] == '2026-11-01 12:30,100.0,Еда,"обед, кафе",расход'


def test_summary(storage):
    when = datetime(2026, 11, 5)
    for e in [
        Entry(600, "Еда", ""),
        Entry(300, "Транспорт", ""),
        Entry(100, "Еда", ""),
        Entry(5000, "Доход", "", is_income=True),
    ]:
        storage.add(1, e, when)
    text = stats.summary(storage.between(1, date(2026, 11, 1), date(2026, 11, 30)), "Ноябрь")
    lines = text.splitlines()
    assert lines[1] == "Расходы: 1 000 сом"
    assert "баланс: 4 000 сом" in lines[2]
    assert lines[3].endswith("Еда: 700 сом (70%)")
    assert lines[4].endswith("Транспорт: 300 сом (30%)")
    assert stats.summary([], "Пусто").endswith("Записей нет.")


def test_month_bounds():
    assert stats.month_bounds(date(2026, 2, 14)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert stats.month_bounds(date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))


@pytest.mark.parametrize(
    "before, now, expected",
    [
        (7000, 7500, None),
        (7900, 8100, "80%"),
        (8100, 8200, None),  # 80% уже пересекли раньше — не повторяем
        (9500, 10200, "превышен"),
        (12000, 13000, None),
    ],
)
def test_budget_warning(before, now, expected):
    result = stats.budget_warning(before, now, 10000)
    assert (result is None) if expected is None else (expected in result)


def test_money_format():
    assert stats.money(1500) == "1 500 сом"
    assert stats.money(320.5) == "320.50 сом"


async def test_sheets_mirror_does_not_crash_bot():
    class FailingClient:
        def open_by_key(self, key):
            raise ConnectionError("no network")

    await SheetsMirror("id", "c.json", client=FailingClient()).append("user", ["x"])
