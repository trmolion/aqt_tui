from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Button, DirectoryTree, Static, RadioSet, RadioButton, Select
from textual import work
from pathlib import Path
from typing import Optional

from scan_server.aqt_interface import AqtConfig, get_available_oses, get_available_platform, run_installation


class Aqt_tui_installer(App):
    CSS_PATH = "styles.tcss"

    def __init__(self):
        super().__init__()
        self.config = AqtConfig()
        self.step = 0
        self.available_oses = get_available_oses()   # список строк: 'windows', 'linux', 'mac'
        self.avaliable_os_platform = get_available_platform()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left_panel"):
                self.config_btn = Button("1. Выбрать конфиг", id="config_btn")
                self.host_os_btn = Button("2. Выбор ОС", id="host_os_btn", disabled=True)
                self.host_platform_btn = Button("3. Выбор платформы", id="host_platform_btn", disabled=True)
                self.version_btn = Button("4. Выбор версии Qt", id="version_btn", disabled=True)
                self.compiler_btn = Button("5. Выбор компилятора", id="compiler_btn", disabled=True)
                self.modules_btn = Button("6. Выбор модулей", id="modules_btn", disabled=True)
                self.path_btn = Button("7. Путь установки", id="path_btn", disabled=True)
                self.install_btn = Button("Установить", id="install_btn", variant="success", disabled=True)

                yield self.config_btn
                yield self.host_os_btn
                yield self.host_platform_btn
                yield self.version_btn
                yield self.compiler_btn
                yield self.modules_btn
                yield self.path_btn
                yield self.install_btn

            with Vertical(id="right_panel"):
                self.main_settings = Static(self._format_settings(), id="main_settings")
                yield self.main_settings
        yield Footer()

    def _format_settings(self) -> str:
        lines = []
        config_str = str(self.config.config_path) if self.config.config_path else "не выбран"
        lines.append(f"Конфиг: {config_str}")
        os_str = self.config.host_os if self.config.host_os else "не выбрана"
        lines.append(f"ОС: {os_str}")
        target_str = self.config.target if self.config.target else "не выбрана (desktop)"
        lines.append(f"Платформа: {target_str}")
        ver_str = self.config.version if self.config.version else "не выбрана"
        lines.append(f"Версия Qt: {ver_str}")
        arch_str = self.config.arch if self.config.arch else "не выбран"
        lines.append(f"Компилятор/архитектура: {arch_str}")
        mods_str = ", ".join(self.config.modules) if self.config.modules else "не выбраны"
        lines.append(f"Модули: {mods_str}")
        path_str = str(self.config.install_path) if self.config.install_path else "не выбран"
        lines.append(f"Путь установки: {path_str}")
        return "\n".join(lines)

    def update_main_settings(self) -> None:
        self.main_settings.update(self._format_settings())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config_btn":
            self.show_file_picker()
        elif event.button.id == "host_os_btn":
            self.show_os_selector()
        elif event.button.id == "os_done_btn":           # обработка кнопки "Применить" выбора ОС
            if self.config.host_os:
                self.update_main_settings()
                self._check_and_unlock()
                self._show_main_settings()
                self.notify(f"Выбрана ОС: {self.config.host_os}")
            else:
                self.notify("Выберите ОС", severity="warning")

    def _check_and_unlock(self) -> None:
        if self.config.config_path:
            self.host_os_btn.disabled = False
        if self.config.host_os:
            self.version_btn.disabled = False
        if self.config.version:
            self.compiler_btn.disabled = False
        if self.config.arch:
            self.modules_btn.disabled = False
        if self.config.modules:
            self.path_btn.disabled = False
        if self.config.install_path:
            self.install_btn.disabled = False

    # === Выбор конфига ===
    def show_file_picker(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        # Не задаём ID, чтобы избежать конфликтов
        tree = DirectoryTree(Path.home())
        right_panel.mount(tree)
        tree.focus()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path
        if path.suffix == ".ini":
            self.config.config_path = path
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            self.notify(f"Конфиг выбран: {path}")
        else:
            self.notify("Выберите файл .ini", severity="warning")

    def _show_main_settings(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        right_panel.mount(self.main_settings)

    # === Выбор ОС ===
    def show_os_selector(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        # Создаём радиокнопки с id, равным имени ОС
        buttons = [RadioButton(os_name.capitalize(), id=os_name) for os_name in self.available_oses]
        radio_set = RadioSet(*buttons, id="os_radio")
        right_panel.mount(radio_set)
        done_btn = Button("Применить", id="os_done_btn")
        right_panel.mount(done_btn)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Сохраняем выбранную ОС (id кнопки = имя ОС)"""
        self.config.host_os = event.pressed.id
    
    # === Выбор платформы ОС ===
    def show_platform_os_selector(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        # Создаём радиокнопки с id, равным имени платформы под ОС
        buttons = [RadioButton(os_platform_name.capitalize(), id=os_platform_name) for os_platform_name in self.avaliable_os_platform]
        radio_set = RadioSet(*buttons, id="os_radio")
        right_panel.mount(radio_set)
        done_btn = Button("Применить", id="os_done_btn")
        right_panel.mount(done_btn)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Сохраняем выбранную платформу ОС"""
        self.config.host_os = event.pressed.id
