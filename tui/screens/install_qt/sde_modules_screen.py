from pathlib import Path
from typing import Callable, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, ProgressBar

from scan_server.aqt_interface import get_sde_modules
from tui.screens.check_list import CheckListWidget

_TITLES = {"doc": "документации", "examples": "примеров"}


class SdeModulesWidget(Widget):
    """Виджет выбора модулей документации или примеров. Монтируется в right_panel."""

    DEFAULT_CSS = "SdeModulesWidget { height: 100%; }"

    def __init__(
        self,
        working_urls: List[str],
        host_os: str,
        version: str,
        flavor: str,  # "doc" или "examples"
        on_done: Callable[[Optional[List[str]]], None],
        cached_modules: Optional[List[str]] = None,
        current_modules: Optional[List[str]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self._working_urls = working_urls
        self._host_os = host_os
        self._version = version
        self._flavor = flavor
        self._on_done = on_done
        self._cached_modules = cached_modules
        self._current_modules = current_modules or []
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        yield Vertical(id="sde_content")

    def on_mount(self) -> None:
        if self._cached_modules is not None:
            self._render_list(self._cached_modules)
        else:
            self._show_loading()
            self._fetch_worker(self._working_urls)

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_loading(self) -> None:
        content = self.query_one("#sde_content")
        content.remove_children()
        container = Vertical(id="loading_container")
        content.mount(container)
        container.mount(Label(f"Загрузка модулей {_TITLES[self._flavor]}..."))
        container.mount(ProgressBar(total=None, show_eta=False))

    def _render_list(self, modules: List[str]) -> None:
        content = self.query_one("#sde_content")
        content.remove_children()
        content.mount(CheckListWidget(
            f"Модули {_TITLES[self._flavor]} Qt {self._version}",
            [(m, m) for m in modules],
            self._on_done,
            selected=self._current_modules,
            hint="Базовый пакет ставится всегда, отметьте дополнительные модули",
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
            modules = get_sde_modules(working_urls, self._host_os, self._version, self._flavor, self._config_path)
        except Exception as e:
            call(self.notify, f"Ошибка получения модулей {_TITLES[self._flavor]}: {e}", severity="error")
            call(self._on_done, None)
            return
        self.app._sde_cache[(self._host_os, self._version, self._flavor)] = modules
        call(self._render_list, modules)
