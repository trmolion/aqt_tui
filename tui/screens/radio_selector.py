from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

from textual.app import ComposeResult
from textual.containers import Center
from textual.markup import escape
from textual.widget import Widget
from textual.widgets import Button, Label, RadioSet, RadioButton


class RadioSelectorWidget(Widget):
    CSS_PATH = "radio_selector.tcss"

    def __init__(
        self,
        title: str,
        options: Sequence[Union[str, Tuple[str, Any]]],
        on_apply: Callable[[Any], None],
        current: Optional[Any] = None,
    ) -> None:
        super().__init__()
        self._title = title
        # строка — значение и подпись сразу; (подпись, значение) — произвольное значение
        self._options: List[Tuple[str, Any]] = [
            (opt.capitalize(), opt) if isinstance(opt, str) else (escape(opt[0]), opt[1]) for opt in options
        ]
        self._on_apply = on_apply
        self._current = current

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="title")
        buttons = [
            RadioButton(label, id=f"opt_{i}", value=(value == self._current))
            for i, (label, value) in enumerate(self._options)
        ]
        yield RadioSet(*buttons, id="radio_options")
        yield Center(Button("Применить", id="apply_btn", variant="success"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()  # не даём событию всплыть до App.on_button_pressed
        if event.button.id != "apply_btn":
            return
        radio_set = self.query_one("#radio_options", RadioSet)
        index = radio_set.pressed_index
        if index >= 0:
            self._on_apply(self._options[index][1])
        else:
            self.notify("Выберите значение", severity="warning")
