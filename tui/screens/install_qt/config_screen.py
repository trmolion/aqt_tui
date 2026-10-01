from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.widget import Widget
from textual.widgets import Button, DirectoryTree, Input, Label, ProgressBar

from scan_server.check_servers import check_single_server, get_urls_from_config
from scan_server.remote_config import DEFAULT_CONFIG_URL, download_config

# (путь к локальной копии конфига, результаты проверки серверов, подпись источника)
ConfigResult = Optional[Tuple[Path, List[Dict[str, Any]], str]]


class ConfigWidget(Widget):
    """
    Виджет выбора конфига: по умолчанию (gist), по ссылке или локальный .ini.
    После загрузки проверяет серверы. Монтируется в right_panel.
    """

    DEFAULT_CSS = """
    ConfigWidget { height: 100%; }
    ConfigWidget Center { width: 100%; height: auto; margin-top: 1; }
    ConfigWidget Center Button { width: 55%; min-width: 20; }
    ConfigWidget .hint { color: $text-muted; text-style: none; content-align: center middle; }
    ConfigWidget #config_url_input { margin-top: 1; }
    """

    def __init__(
        self,
        on_done: Callable[[ConfigResult], None],
        initial_path: Optional[Path] = None,
        initial_label: str = "",
    ) -> None:
        super().__init__()
        self._on_done = on_done
        self._initial_path = initial_path
        self._initial_label = initial_label

    def compose(self) -> ComposeResult:
        yield Vertical(id="config_content")

    def on_mount(self) -> None:
        if self._initial_path:
            self._load(path=self._initial_path, label=self._initial_label)
        else:
            self._show_source_choice()

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_source_choice(self) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        default_btn = Button("Конфиг по умолчанию", id="cfg_default", variant="success")
        content.mount(
            Label("Откуда взять конфиг?"),
            Center(default_btn),
            Label(DEFAULT_CONFIG_URL, classes="hint"),
            Center(Button("Удалённый конфиг по ссылке", id="cfg_remote", variant="primary")),
            Center(Button("Локальный файл", id="cfg_local", variant="primary")),
        )
        self.call_after_refresh(default_btn.focus)

    def _show_url_input(self) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        url_input = Input(placeholder="https://gist.github.com/<user>/<id>", id="config_url_input")
        content.mount(
            Label("Ссылка на .ini-файл или страницу GitHub Gist:"),
            url_input,
            Center(Button("Загрузить", id="cfg_remote_load", variant="success")),
            Center(Button("Назад", id="cfg_back")),
        )
        self.call_after_refresh(url_input.focus)

    def _show_file_picker(self) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        tree = DirectoryTree(Path.home(), id="config_tree")
        content.mount(Center(Button("Назад", id="cfg_back")), tree)
        self.call_after_refresh(tree.focus)

    def _show_loading(self, text: str) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        container = Vertical(id="loading_container")
        content.mount(container)
        container.mount(Label(text))
        container.mount(ProgressBar(total=None, show_eta=False))

    def _show_progress(self, total: int) -> None:
        content = self.query_one("#config_content")
        content.remove_children()
        container = Vertical(id="progress_container")
        content.mount(container)
        container.mount(Label("Проверка серверов..."))
        self._progress_bar = ProgressBar(total=total, show_eta=False)
        container.mount(self._progress_bar)

    # -------------------------------------------------------------------------
    # Выбор источника
    # -------------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id not in ("cfg_default", "cfg_remote", "cfg_local", "cfg_remote_load", "cfg_back"):
            return
        event.stop()
        if button_id == "cfg_default":
            self._load(url=DEFAULT_CONFIG_URL, label="по умолчанию (gist)")
        elif button_id == "cfg_remote":
            self._show_url_input()
        elif button_id == "cfg_local":
            self._show_file_picker()
        elif button_id == "cfg_remote_load":
            self._load_from_input()
        elif button_id == "cfg_back":
            self._show_source_choice()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "config_url_input":
            event.stop()
            self._load_from_input()

    def _load_from_input(self) -> None:
        url = self.query_one("#config_url_input", Input).value.strip()
        if not url.startswith(("http://", "https://")):
            self.notify("Введите ссылку, начинающуюся с http:// или https://", severity="warning")
            return
        self._load(url=url, label=url)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        event.stop()
        if event.path.suffix == ".ini":
            self._load(path=event.path, label=str(event.path))
        else:
            self.notify("Выберите файл .ini", severity="warning")

    # -------------------------------------------------------------------------
    # Загрузка конфига и проверка серверов
    # -------------------------------------------------------------------------

    def _load(self, label: str, url: Optional[str] = None, path: Optional[Path] = None) -> None:
        self._show_loading("Загрузка конфига..." if url else "Чтение конфига...")
        self._load_worker(label, url, path)

    def _if_attached(self, callback: Callable, *args, **kwargs) -> None:
        """Воркер может закончить работу, когда виджет уже убран с экрана — тогда результат не нужен."""
        if self.is_attached:
            callback(*args, **kwargs)

    @work(thread=True, exclusive=True)
    def _load_worker(self, label: str, url: Optional[str], path: Optional[Path]) -> None:
        def call(callback: Callable, *args, **kwargs) -> None:
            self.app.call_from_thread(self._if_attached, callback, *args, **kwargs)

        try:
            if url:
                path = download_config(url)
            urls = get_urls_from_config(path)
        except Exception as e:
            call(self.notify, f"Не удалось загрузить конфиг: {e}", severity="error")
            call(self._show_source_choice)
            return
        if not urls:
            call(self.notify, "В конфиге нет ни baseurl, ни fallbacks", severity="error")
            call(self._show_source_choice)
            return

        call(self._show_progress, len(urls))
        results: List[Dict[str, Any]] = []
        for i, server_url in enumerate(urls):
            results.append(check_single_server(server_url))
            call(self._update_progress, i + 1, len(urls), server_url)
        call(self._on_verification_done, path, results, label)

    def _update_progress(self, current: int, total: int, url: str = "") -> None:
        self._progress_bar.update(progress=current, total=total)
        self.query_one("#progress_container Label", Label).update(
            f"Проверка серверов... ({current}/{total})   {url}"
        )

    def _on_verification_done(self, path: Path, results: List[Dict[str, Any]], label: str) -> None:
        if any(r["status"] for r in results):
            self._on_done((path, results, label))
        else:
            self._show_source_choice()
            self.notify("Не удалось подключиться ни к одному серверу", severity="error")
