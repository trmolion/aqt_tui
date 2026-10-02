from typing import Any, Callable, Hashable, List, Sequence, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Label, SelectionList


class CheckListWidget(Widget):
    """Переиспользуемый список с галочками + кнопки «Выбрать всё» и «Применить»."""

    DEFAULT_CSS = """
    CheckListWidget { height: 100%; }
    CheckListWidget .hint { color: $text-muted; text-style: none; }
    CheckListWidget SelectionList { height: 1fr; margin-top: 1; }
    /* по умолчанию невыбранный пункт — тёмный X, его путают с отмеченным: делаем пустой квадрат */
    CheckListWidget SelectionList > .selection-list--button,
    CheckListWidget SelectionList > .selection-list--button-highlighted { color: $panel; }
    CheckListWidget SelectionList > .selection-list--button-selected,
    CheckListWidget SelectionList > .selection-list--button-selected-highlighted {
        color: $text-success;
        text-style: bold;
    }
    CheckListWidget #check_list_buttons { height: auto; align: center middle; margin-top: 1; }
    CheckListWidget #check_list_buttons Button { width: 40%; min-width: 16; margin: 0 1; }
    """

    def __init__(
        self,
        title: str,
        items: Sequence[Tuple[str, Hashable]],
        on_apply: Callable[[List[Any]], None],
        selected: Sequence[Hashable] = (),
        hint: str = "",
        allow_empty: bool = True,
    ) -> None:
        super().__init__()
        self._title = title
        self._items = items
        self._on_apply = on_apply
        self._selected = set(selected)
        self._hint = hint
        self._allow_empty = allow_empty

    def compose(self) -> ComposeResult:
        yield Label(self._title)
        if self._hint:
            yield Label(self._hint, classes="hint")
        yield Label("Пробел, Enter или клик — отметить пункт", classes="hint")
        yield SelectionList(*[(prompt, value, value in self._selected) for prompt, value in self._items])
        with Horizontal(id="check_list_buttons"):
            yield Button("Выбрать всё", id="check_list_all", variant="primary")
            yield Button("Применить", id="check_list_apply", variant="success")

    def on_mount(self) -> None:
        self.query_one(SelectionList).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id not in ("check_list_all", "check_list_apply"):
            return
        event.stop()
        selection_list = self.query_one(SelectionList)
        if event.button.id == "check_list_all":
            selection_list.select_all()
            return
        # Порядок как в списке, а не как отмечали
        chosen = set(selection_list.selected)
        selected = [value for _, value in self._items if value in chosen]
        if not selected and not self._allow_empty:
            self.notify("Отметьте хотя бы один пункт", severity="warning")
            return
        self._on_apply(selected)
