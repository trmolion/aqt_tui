import re
from pathlib import Path
from typing import Callable, Optional

from textual.containers import Horizontal
from textual.app import ComposeResult
from textual.markup import escape
from textual.widget import Widget
from textual.widgets import Button, Checkbox, DirectoryTree, Input, Label

# запрещаем: слэши, нулевой байт, и прочие спецсимволы файловой системы
_INVALID_FOLDER_RE = re.compile(r'[/\\\x00<>:"|?*]')


class PathWidget(Widget):
    """Виджет выбора пути установки Qt."""

    DEFAULT_CSS = """
    PathWidget { height: 100%; }
    PathWidget #path_actions { height: auto; align: center middle; margin-top: 1; }
    PathWidget #accept_path_btn { width: 55%; min-width: 20; margin: 0; }
    PathWidget #make_dir_check { margin-left: 2; }
    PathWidget #install_path_label {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        margin: 1 0 0 0;
    }
    """

    def __init__(
        self,
        on_done: Callable[[Optional[Path]], None],
        current_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self._on_done = on_done
        self._selected_path: Optional[Path] = current_path

    def compose(self) -> ComposeResult:
        yield Label(self._path_markup(self._selected_path), id="install_path_label")
        with Horizontal(id="path_actions"):
            yield Button("Принять путь", id="accept_path_btn", variant="success")
            yield Checkbox("Создать папку", id="make_dir_check")
        yield Input(placeholder="Имя папки", id="folder_name_input")
        yield DirectoryTree(Path.home())

    def on_mount(self) -> None:
        self.query_one("#folder_name_input", Input).styles.display = "none"
        self.query_one(DirectoryTree).focus()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        event.stop()
        self._selected_path = event.path
        self.query_one("#install_path_label", Label).update(self._path_markup(event.path))

    @staticmethod
    def _path_markup(path: Optional[Path]) -> str:
        if path is None:
            return "Путь: [dim]не выбран[/]"
        return f"Путь: [$accent]{escape(str(path))}[/]"

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()
        folder_input = self.query_one("#folder_name_input", Input)
        if event.value:
            folder_input.styles.display = "block"
            folder_input.focus()
        else:
            folder_input.styles.display = "none"
            folder_input.value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "accept_path_btn":
            return
        event.stop()
        if self._selected_path is None:
            self.notify("Сначала выберите путь в дереве", severity="warning")
            return
        make_dir = self.query_one("#make_dir_check", Checkbox).value
        if make_dir:
            folder_name = self.query_one("#folder_name_input", Input).value.strip()
            if not folder_name:
                self.notify("Введите имя папки", severity="warning")
                return
            if _INVALID_FOLDER_RE.search(folder_name):
                self.notify("Имя папки содержит недопустимые символы: / \\ < > : \" | ? *", severity="warning")
                return
            final_path = self._selected_path / folder_name
        else:
            final_path = self._selected_path
        self._on_done(final_path)
