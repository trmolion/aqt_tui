from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Digits, Label, Button, Footer

class ClockApp(App):
    # CSS = """
    # Screen { align: right top; }
    # Digits { width: auto; }
    # """
    CSS_PATH = "styles.tcss"
    
    
    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield Vertical(
                    Label("Время"),
                    Digits(""),
                    id = "clock_card"
                )
                yield Vertical(
                    Label("Действия"),
                    Button("Обновить", id="refresh", variant="primary"),
                    id="actions_card"
                )
            yield Vertical(
                Label("Информация"),
                id="info_card"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.update_clock()
            self.query_one("#info_card", Vertical).mount(Label("Обновлено!"))

    def on_ready(self) -> None:
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self) -> None:
        clock = datetime.now().time()
        self.query_one(Digits).update(f"{clock:%T}")