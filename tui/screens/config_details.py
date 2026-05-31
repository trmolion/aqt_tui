from typing import Any, Callable, Dict, List

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Center
from textual.widget import Widget
from textual.widgets import Button, Static


class ConfigDetailsWidget(Widget):
    """Виджет деталей проверки серверов конфига."""

    DEFAULT_CSS = """
    ConfigDetailsWidget { height: 100%; }
    ConfigDetailsWidget Center { width: 100%; margin-top: 1; }
    ConfigDetailsWidget Button#refresh_config_check { width: 55%; min-width: 20; }
    """

    def __init__(
        self,
        server_results: List[Dict[str, Any]],
        on_refresh: Callable[[], None],
    ) -> None:
        super().__init__()
        self._server_results = server_results
        self._on_refresh = on_refresh

    def compose(self) -> ComposeResult:
        lines = ["[bold]Результаты проверки серверов:[/]", ""]
        for item in self._server_results:
            status_icon = "[green]●[/]" if item["status"] else "[red]●[/]"
            resp_time = item["response_time"]
            time_str = f"{resp_time:.3f} с" if resp_time is not None else "—"
            lines += [
                f"{status_icon} {item['url']}",
                f"\tВремя ответа: {time_str}",
                f"\tКод ответа: {item['status_code']}",
            ]
            if item["error"]:
                lines.append(f"   Ошибка: {item['error']}")
            lines.append("")
        with ScrollableContainer():
            yield Static("\n".join(lines), id="config_details")
            yield Center(Button("Обновить проверку", id="refresh_config_check", variant="primary"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh_config_check":
            event.stop()
            self._on_refresh()
