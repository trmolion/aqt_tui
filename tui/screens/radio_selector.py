from typing import Callable, List, Optional

from textual.app import ComposeResult
from textual.containers import Center
from textual.widget import Widget
from textual.widgets import Button, Label, RadioSet, RadioButton


class RadioSelectorWidget(Widget):
    CSS_PATH = "radio_selector.tcss"

    def __init__(
        self,
        title: str,
        options: List[str],
        on_apply: Callable[[str], None],
        current: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._options = options
        self._on_apply = on_apply
        self._current = current

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="title")
        buttons = [
            RadioButton(opt.capitalize(), id=opt, value=(opt == self._current))
            for opt in self._options
        ]
        yield RadioSet(*buttons, id="radio_options")
        yield Center(Button("Применить", id="apply_btn", variant="success"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()  # не даём событию всплыть до App.on_button_pressed
        if event.button.id != "apply_btn":
            return
        radio_set = self.query_one("#radio_options", RadioSet)
        selected: Optional[str] = None
        for btn in radio_set.query(RadioButton):
            if btn.value:
                selected = btn.id
                break
        if selected:
            self._on_apply(selected)
        else:
            self.notify("Выберите значение", severity="warning")
