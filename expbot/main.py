import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message

from expbot import stats
from expbot.config import Settings
from expbot.parser import CATEGORIES, ParseError, parse_amount, parse_message
from expbot.sheets import SheetsMirror
from expbot.storage import Storage

HELP = (
    "Пишите траты обычным сообщением:\n"
    "• <code>450 обед</code>\n• <code>такси 250</code>\n• <code>1.5к продукты</code>\n"
    "• <code>+50000 зарплата</code> — доход\n\n"
    "/today — за сегодня\n/week — за 7 дней\n/month — за месяц\n"
    "/budget 30000 — месячный бюджет\n/undo — удалить последнюю запись\n"
    "/export — выгрузка в CSV\n/categories — категории"
)


def build_router(storage: Storage, tz: ZoneInfo, sheets: SheetsMirror | None = None) -> Router:
    router = Router()

    def now() -> datetime:
        return datetime.now(tz).replace(tzinfo=None, microsecond=0)

    def month_spent(user_id: int) -> float:
        start, end = stats.month_bounds(now().date())
        return sum(
            s.entry.amount for s in storage.between(user_id, start, end) if not s.entry.is_income
        )

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def start(message: Message) -> None:
        await message.answer("Привет! Я веду учёт расходов.\n\n" + HELP, parse_mode="HTML")

    @router.message(Command("categories"))
    async def categories(message: Message) -> None:
        lines = [f"<b>{c}</b>: {', '.join(k[:4])}…" for c, k in CATEGORIES.items()]
        await message.answer("\n".join(lines), parse_mode="HTML")

    @router.message(Command("today", "week", "month"))
    async def report(message: Message, command: CommandObject) -> None:
        today = now().date()
        if command.command == "today":
            start, end, title = today, today, f"Сегодня, {today:%d.%m}"
        elif command.command == "week":
            start, end, title = today - timedelta(days=6), today, "Последние 7 дней"
        else:
            start, end = stats.month_bounds(today)
            title = f"Месяц {today:%m.%Y}"
        text = stats.summary(storage.between(message.from_user.id, start, end), title)
        budget = storage.get_budget(message.from_user.id)
        if command.command == "month" and budget:
            left = budget - month_spent(message.from_user.id)
            text += f"\n\nБюджет: {stats.money(budget)}, осталось {stats.money(left)}"
        await message.answer(text)

    @router.message(Command("budget"))
    async def budget(message: Message, command: CommandObject) -> None:
        parsed = parse_amount(command.args or "")
        if not parsed:
            current = storage.get_budget(message.from_user.id)
            await message.answer(
                f"Текущий бюджет: {stats.money(current)}" if current else "Пример: /budget 30000"
            )
            return
        storage.set_budget(message.from_user.id, parsed[0])
        await message.answer(f"Месячный бюджет: {stats.money(parsed[0])}")

    @router.message(Command("undo"))
    async def undo(message: Message) -> None:
        removed = storage.undo_last(message.from_user.id)
        if removed is None:
            await message.answer("Удалять нечего.")
        else:
            e = removed.entry
            await message.answer(f"Удалено: {stats.money(e.amount)} · {e.category} {e.comment}")

    @router.message(Command("export"))
    async def export(message: Message) -> None:
        data = storage.export_csv(message.from_user.id)
        await message.answer_document(BufferedInputFile(data, filename="expenses.csv"))

    @router.message(F.text & ~F.text.startswith("/"))
    async def add(message: Message) -> None:
        try:
            entry = parse_message(message.text)
        except ParseError as e:
            await message.answer(str(e))
            return
        user_id = message.from_user.id
        before = month_spent(user_id)
        saved = storage.add(user_id, entry, now())
        kind = "💰 Доход" if entry.is_income else "✅ Расход"
        await message.answer(f"{kind}: {stats.money(entry.amount)} · {entry.category}")
        if not entry.is_income:
            warning = stats.budget_warning(
                before, before + entry.amount, storage.get_budget(user_id)
            )
            if warning:
                await message.answer(warning)
        if sheets:
            row = [
                saved.created_at.strftime("%Y-%m-%d %H:%M"),
                entry.amount,
                entry.category,
                entry.comment,
                "доход" if entry.is_income else "расход",
            ]
            await sheets.append(message.from_user.full_name, row)

    return router


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    storage = Storage(settings.database_path)
    sheets = (
        SheetsMirror(settings.google_sheet_id, settings.google_credentials_file)
        if settings.google_sheet_id
        else None
    )
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(build_router(storage, ZoneInfo(settings.timezone), sheets))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
