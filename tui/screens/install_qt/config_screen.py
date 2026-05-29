from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import DirectoryTree, Label, ProgressBar

from scan_server.check_servers import check_single_server, get_urls_from_config

ConfigResult = Optional[Tuple[Path, List[Dict[str, Any]]]]


class ConfigWidget(Widget):
    """Виджет выбора .ini-конфига + проверки серверов. Монтируется в right_panel."""

    DEFAULT_CSS = "ConfigWidget { height: 100%; }"

    def __init__(
        self,
        on_done: Callable[[ConfigResult], None],
        initial_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self._on_done = on_done
        self._initial_path = initial_path
        self._pending_path: Optional[Path] = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="config_content")

    def on_mount(self) -> None:
        self._pending_path = self._initial_path
        if self._initial_path:
            self._start_verification(self._initial_path)
        else:
            self._show_file_picker()

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_file_picker(self) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        tree = DirectoryTree(Path.home(), id="config_tree")
        content.mount(tree)
        tree.focus()

    def _show_progress(self, total: int) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        container = Vertical(id="progress_container")
        content.mount(container)
        container.mount(Label("Проверка серверов..."))
        self._progress_bar = ProgressBar(total=total, show_eta=False)
        container.mount(self._progress_bar)

    # -------------------------------------------------------------------------
    # Выбор файла
    # -------------------------------------------------------------------------

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        if event.path.suffix == ".ini":
            self._pending_path = event.path
            self._start_verification(event.path)
        else:
            self.notify("Выберите файл .ini", severity="warning")

    # -------------------------------------------------------------------------
    # Проверка серверов
    # -------------------------------------------------------------------------

    def _start_verification(self, config_path: Path) -> None:
        urls = get_urls_from_config(config_path)
        self._show_progress(len(urls))
        self._verify_worker(urls)

    @work(thread=True)
    def _verify_worker(self, urls: List[str]) -> None:
        total = len(urls)
        results: List[Dict[str, Any]] = []
        for i, url in enumerate(urls):
            results.append(check_single_server(url))
            self.app.call_from_thread(self._update_progress, i + 1, total, url)
        self.app.call_from_thread(self._on_verification_done, results)

    def _update_progress(self, current: int, total: int, url: str = "") -> None:
        if hasattr(self, "_progress_bar"):
            self._progress_bar.update(progress=current, total=total)
        self.query_one("#progress_container Label", Label).update(
            f"Проверка серверов... ({current}/{total})   {url}"
        )

    def _on_verification_done(self, results: List[Dict[str, Any]]) -> None:
        if any(r["status"] for r in results):
            available = sum(1 for r in results if r["status"])
            self.notify(f"Доступны {available} из {len(results)} серверов")
            self._on_done((self._pending_path, results))
        else:
            self._show_file_picker()
            self.notify("Не удалось подключиться ни к одному серверу", severity="error")
