from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, ProgressBar

from scan_server.aqt_interface import get_tools_info
from tui.screens.check_list import CheckListWidget


class ToolsWidget(Widget):
    """Виджет выбора инструментов (CMake, Ninja, …). Монтируется в right_panel."""

    DEFAULT_CSS = "ToolsWidget { height: 100%; }"

    def __init__(
        self,
        working_urls: List[str],
        host_os: str,
        on_done: Callable[[Optional[List[Tuple[str, str]]]], None],
        cached_tools: Optional[List[Dict[str, str]]] = None,
        current_tools: Optional[List[Tuple[str, str]]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self._working_urls = working_urls
        self._host_os = host_os
        self._on_done = on_done
        self._cached_tools = cached_tools
        self._current_tools = current_tools or []
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        yield Vertical(id="tools_content")

    def on_mount(self) -> None:
        if self._cached_tools:
            self._render_list(self._cached_tools)
        else:
            self._show_loading()
            self._fetch_worker(self._working_urls)

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_loading(self) -> None:
        content = self.query_one("#tools_content")
        content.remove_children()
        container = Vertical(id="loading_container")
        content.mount(container)
        container.mount(Label("Загрузка списка инструментов..."))
        container.mount(ProgressBar(total=None, show_eta=False))

    def _render_list(self, tools: List[Dict[str, str]]) -> None:
        content = self.query_one("#tools_content")
        content.remove_children()
        content.mount(CheckListWidget(
            "Выбор инструментов",
            [(t["title"], (t["tool"], t["variant"])) for t in tools],
            self._on_done,
            selected=[tuple(t) for t in self._current_tools],
            allow_empty=False,
        ))

    # -------------------------------------------------------------------------
    # Загрузка данных
    # -------------------------------------------------------------------------

    def _if_attached(self, callback: Callable, *args, **kwargs) -> None:
        if self.is_attached:
            callback(*args, **kwargs)

    @work(thread=True)
    def _fetch_worker(self, working_urls: List[str]) -> None:
        def call(callback: Callable, *args, **kwargs) -> None:
            self.app.call_from_thread(self._if_attached, callback, *args, **kwargs)

        try:
            tools = get_tools_info(working_urls, self._host_os, self._config_path)
        except Exception as e:
            call(self.notify, f"Ошибка получения инструментов: {e}", severity="error")
            call(self._on_done, None)
            return
        if not tools:
            call(self.notify, "Нет доступных инструментов для выбранной ОС", severity="warning")
            call(self._on_done, None)
            return
        self.app._tools_cache[self._host_os] = tools
        call(self._render_list, tools)
