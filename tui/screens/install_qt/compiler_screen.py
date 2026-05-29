from typing import Callable, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, ProgressBar

from scan_server.aqt_interface import get_available_architectures
from tui.screens.radio_selector import RadioSelectorWidget


class CompilerWidget(Widget):
    """Виджет выбора компилятора/архитектуры. Монтируется в right_panel."""

    DEFAULT_CSS = "CompilerWidget { height: 100%; }"

    def __init__(
        self,
        working_urls: List[str],
        host_os: str,
        platform: str,
        version: str,
        on_done: Callable[[Optional[str]], None],
        cached_arches: Optional[List[str]] = None,
        current_arch: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._working_urls = working_urls
        self._host_os = host_os
        self._platform = platform
        self._version = version
        self._on_done = on_done
        self._cached_arches = cached_arches
        self._current_arch = current_arch

    def compose(self) -> ComposeResult:
        yield Vertical(id="compiler_content")

    def on_mount(self) -> None:
        if self._cached_arches:
            self._render_selector(self._cached_arches)
        else:
            self._show_loading()
            self._fetch_worker(self._working_urls)

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_loading(self) -> None:
        content = self.query_one("#compiler_content")
        content.remove_children()
        container = Vertical(id="loading_container")
        content.mount(container)
        container.mount(Label("Загрузка архитектур..."))
        container.mount(ProgressBar(total=None, show_eta=False))

    def _render_selector(self, arches: List[str]) -> None:
        content = self.query_one("#compiler_content")
        content.remove_children()
        content.mount(RadioSelectorWidget(
            "Выбор компилятора/архитектуры",
            arches,
            self._on_done,
            self._current_arch,
        ))

    # -------------------------------------------------------------------------
    # Загрузка данных
    # -------------------------------------------------------------------------

    @work(thread=True)
    def _fetch_worker(self, working_urls: List[str]) -> None:
        try:
            arches = get_available_architectures(
                working_urls, self._host_os, self._platform, self._version
            )
            if not arches:
                self.app.call_from_thread(
                    self.notify, "Нет доступных архитектур для выбранной версии", severity="warning"
                )
                self.app.call_from_thread(self._on_done, None)
                return
            self.app._arches_cache[(self._host_os, self._platform, self._version)] = arches
            self.app.call_from_thread(self._render_selector, arches)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Ошибка получения архитектур: {e}", severity="error")
            self.app.call_from_thread(self._on_done, None)
