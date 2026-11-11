import asyncio
import logging

log = logging.getLogger(__name__)


class SheetsMirror:
    """Дублирует каждую запись в Google Таблицу (по листу на пользователя)."""

    HEADER = ["Дата", "Сумма", "Категория", "Комментарий", "Тип"]

    def __init__(self, sheet_id: str, credentials_file: str, client=None) -> None:
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self._client = client
        self._sheets: dict[str, object] = {}

    def _worksheet(self, name: str):
        if name not in self._sheets:
            import gspread

            if self._client is None:
                self._client = gspread.service_account(filename=self.credentials_file)
            book = self._client.open_by_key(self.sheet_id)
            try:
                ws = book.worksheet(name)
            except gspread.WorksheetNotFound:
                ws = book.add_worksheet(name, rows=1000, cols=len(self.HEADER))
                ws.append_row(self.HEADER)
            self._sheets[name] = ws
        return self._sheets[name]

    async def append(self, user_name: str, row: list) -> None:
        try:
            await asyncio.to_thread(lambda: self._worksheet(user_name).append_row(row))
        except Exception:
            # Таблица — копия для удобства; основная база — SQLite, поэтому не роняем бота
            log.exception("Не удалось записать в Google Sheets")
