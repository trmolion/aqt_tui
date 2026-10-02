from pathlib import Path
from typing import Callable, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, ProgressBar

from qt_scanner.scanner import InstalledQt, installed_modules
from scan_server.aqt_interface import resolve_installed_arch
from tui.screens.install_qt.modules_screen import ModulesWidget


class ExistingQtModulesWidget(Widget):
    """
    Доустановка модулей к найденному Qt: определяет его архитектуру на сервере,
    затем показывает таблицу модулей, где уже установленные отмечены и не снимаются.
    """

    DEFAULT_CSS = "ExistingQtModulesWidget { height: 100%; }"

    def __init__(
        self,
        qt: InstalledQt,
        working_urls: List[str],
        on_done: Callable[[Optional[List[str]]], None],
        current_modules: Optional[List[str]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self._qt = qt
        self._working_urls = working_urls
        self._on_done = on_done
        self._current_modules = current_modules
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        yield Vertical(id="existing_content")

    def on_mount(self) -> None:
        if self._qt.arch:
            self._render_modules()
        else:
            self._show_loading()
            self._resolve_worker()

    def _show_loading(self) -> None:
        content = self.query_one("#existing_content")
        content.mount(Label(f"Определение архитектуры {self._qt.title}..."))
        content.mount(ProgressBar(total=None, show_eta=False))

    def _render_modules(self) -> None:
        qt = self._qt
        content = self.query_one("#existing_content")
        content.remove_children()
        content.mount(ModulesWidget(
            self._working_urls, qt.host_os, qt.target, qt.version, qt.arch, self._on_done,
            cached_modules=self.app._modules_cache.get((qt.host_os, qt.target, qt.version, qt.arch)),
            current_modules=self._current_modules,
            config_path=self._config_path,
            # читаем с диска при каждом открытии — после доустановки список обновится
            installed_modules=installed_modules(qt.prefix),
        ))

    def _if_attached(self, callback: Callable, *args, **kwargs) -> None:
        if self.is_attached:
            callback(*args, **kwargs)

    @work(thread=True)
    def _resolve_worker(self) -> None:
        def call(callback: Callable, *args, **kwargs) -> None:
            self.app.call_from_thread(self._if_attached, callback, *args, **kwargs)

        qt = self._qt
        try:
            qt.host_os, qt.target, qt.arch = resolve_installed_arch(
                self._working_urls, self.app.detected_host_os, qt.version, qt.arch_dir, self._config_path,
            )
        except Exception as e:
            call(self.notify, f"Не удалось определить архитектуру: {e}", severity="error")
            call(self._on_done, None)
            return
        call(self._render_modules)
