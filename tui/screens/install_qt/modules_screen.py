from typing import Callable, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.coordinate import Coordinate
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, ProgressBar

from scan_server.aqt_interface import get_available_modules


class ModulesWidget(Widget):
    """Виджет выбора модулей Qt. Монтируется в right_panel."""

    DEFAULT_CSS = "ModulesWidget { height: 100%; }"

    def __init__(
        self,
        working_urls: List[str],
        host_os: str,
        platform: str,
        version: str,
        arch: str,
        on_done: Callable[[Optional[List[str]]], None],
        cached_modules=None,
        current_modules: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._working_urls = working_urls
        self._host_os = host_os
        self._platform = platform
        self._version = version
        self._arch = arch
        self._on_done = on_done
        self._cached_modules = cached_modules
        self._current_modules = current_modules or []
        self._sort_reverse = False
        self._last_sort_column = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="modules_content")

    def on_mount(self) -> None:
        if self._cached_modules:
            self._render_table(self._cached_modules)
        else:
            self._show_loading()
            self._fetch_worker(self._working_urls)

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_loading(self) -> None:
        content = self.query_one("#modules_content")
        content.remove_children()
        container = Vertical(id="loading_container")
        content.mount(container)
        container.mount(Label("Загрузка списка модулей..."))
        container.mount(ProgressBar(total=None, show_eta=False))

    def _render_table(self, module_data) -> None:
        content = self.query_one("#modules_content")
        content.remove_children()

        table = DataTable(id="modules_table")
        table.add_columns(
            ("Выбрать", "select"),
            ("Модуль", "module"),
            ("Описание", "description"),
            ("Дата релиза", "release_date"),
            ("Размер загрузки", "compressed_size"),
            ("Размер установки", "uncompressed_size"),
        )
        table.cursor_type = "row"

        for module_name, info in module_data.table_data.items():
            checkbox = "☑" if module_name in self._current_modules else "☐"
            table.add_row(
                checkbox, module_name,
                info.get("DisplayName", ""),
                info.get("ReleaseDate", ""),
                info.get("CompressedSize", ""),
                info.get("UncompressedSize", ""),
                key=module_name,
            )

        wrapper = ScrollableContainer()
        content.mount(wrapper)
        wrapper.mount(table)
        wrapper.mount(Button("Выбрать всё", id="select_all_modules"))
        wrapper.mount(Button("Применить", id="modules_done_btn"))

        table.sort(key=lambda row: self._parse_size(row[4]), reverse=True)
        table.focus()

    # -------------------------------------------------------------------------
    # Загрузка данных
    # -------------------------------------------------------------------------

    @work(thread=True)
    def _fetch_worker(self, working_urls: List[str]) -> None:
        try:
            module_data = get_available_modules(
                working_urls, self._host_os, self._platform, self._version, self._arch
            )
            if not module_data:
                self.app.call_from_thread(
                    self.notify, "Нет доступных модулей для выбранной конфигурации", severity="warning"
                )
                self.app.call_from_thread(self._on_done, None)
                return
            self.app._modules_cache[
                (self._host_os, self._platform, self._version, self._arch)
            ] = module_data
            self.app.call_from_thread(self._render_table, module_data)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Ошибка получения модулей: {e}", severity="error")
            self.app.call_from_thread(self._on_done, None)

    # -------------------------------------------------------------------------
    # События таблицы
    # -------------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.CellSelected) -> None:
        event.stop()
        table = event.data_table
        col_index = table.get_column_index("select")
        current = table.get_row_at(event.cursor_row)[col_index]
        table.update_cell_at(Coordinate(event.cursor_row, col_index), "☑" if current == "☐" else "☐")

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        event.stop()
        if event.column_key not in ("compressed_size", "uncompressed_size"):
            return
        if self._last_sort_column == event.column_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_reverse = False
        self._last_sort_column = event.column_key
        event.data_table.sort(event.column_key, key=self._parse_size, reverse=self._sort_reverse)

    # -------------------------------------------------------------------------
    # Кнопки
    # -------------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select_all_modules":
            event.stop()
            table = self.query_one("#modules_table", DataTable)
            col_index = table.get_column_index("select")
            for row_index in range(len(table.rows)):
                table.update_cell_at(Coordinate(row_index, col_index), "☑")
        elif event.button.id == "modules_done_btn":
            event.stop()
            table = self.query_one("#modules_table", DataTable)
            col_index = table.get_column_index("select")
            selected = [
                table.get_row(row_key)[1]
                for row_key in table.rows
                if table.get_row(row_key)[col_index] == "☑"
            ]
            self._on_done(selected)

    # -------------------------------------------------------------------------
    # Вспомогательное
    # -------------------------------------------------------------------------

    def _parse_size(self, size_str: str) -> float:
        if not size_str:
            return 0.0
        s = size_str.strip().upper()
        multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        if s[-1] in multipliers:
            return float(s[:-1]) * multipliers[s[-1]]
        return float(s)
