from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Header, Footer, Button, Static
from pathlib import Path
from typing import Dict, List, Any, Optional

from scan_server.aqt_interface import AqtConfig, get_available_oses, get_available_platform
from tui.screens import (
    RadioSelectorWidget,
    ConfigWidget, VersionWidget, CompilerWidget, ModulesWidget, ProgressWidget, PathWidget,
    ConfigDetailsWidget,
)


class AqtTuiApp(App):
    CSS_PATH = ["styles.tcss", "screens/radio_selector.tcss"]

    # --- Разделяемое reactive-состояние ---
    language: reactive[str] = reactive("ru")
    installed_qts: reactive[list] = reactive(list)

    def __init__(self):
        super().__init__()
        self.install_config = AqtConfig()
        self.current_section = "main"
        self.available_oses = get_available_oses()

        # Кеш результатов проверки серверов (загружается один раз)
        self._server_results: List[Dict[str, Any]] = []

        # Кеш метаданных: ключ — кортеж параметров конфига
        self._versions_cache: Dict = {}   # (host_os, platform) → tree_dict
        self._arches_cache: Dict = {}     # (host_os, platform, version) → list
        self._modules_cache: Dict = {}    # (host_os, platform, version, arch) → module_data

        self.modules_done = False

    # =========================================================================
    # Compose
    # =========================================================================

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="left_panel"):
                self.config_btn = Button("1. Выбрать конфиг", id="config_btn")
                self.more_inf_config_btn = Button("Подробности конфига", id="more_inf_config_btn", disabled=True)
                self.host_os_btn = Button("2. Выбор ОС", id="host_os_btn", disabled=True)
                self.host_platform_btn = Button("3. Выбор платформы", id="host_platform_btn", disabled=True)
                self.version_btn = Button("4. Выбор версии Qt", id="version_btn", disabled=True)
                self.compiler_btn = Button("5. Выбор компилятора", id="compiler_btn", disabled=True)
                self.modules_btn = Button("6. Выбор модулей", id="modules_btn", disabled=True)
                self.path_btn = Button("7. Путь установки", id="path_btn", disabled=True)
                self.install_btn = Button("Установить", id="install_btn", variant="success", disabled=True)

                yield self.config_btn
                yield self.more_inf_config_btn
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

    # =========================================================================
    # Настройки (summary)
    # =========================================================================

    def _format_settings(self) -> str:
        c = self.install_config
        lines = [
            f"Конфиг: {c.config_path or 'не выбран'}",
            f"ОС: {c.host_os or 'не выбрана'}",
            f"Платформа: {c.platform_host_os or 'не выбрана'}",
            f"Версия Qt: {c.version or 'не выбрана'}",
            f"Компилятор/архитектура: {c.arch or 'не выбран'}",
            f"Модули: {', '.join(c.modules) if c.modules else 'не выбраны'}",
            f"Путь установки: {c.install_path or 'не выбран'}",
        ]
        return "\n".join(lines)

    def update_main_settings(self) -> None:
        self.main_settings.update(self._format_settings())

    # =========================================================================
    # Обработчик кнопок
    # =========================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.current_section != "main" and event.button.id == self.current_section:
            self._show_main_settings()
            return

        btn = event.button.id

        if btn == "config_btn":
            self.show_file_picker()
        elif btn == "more_inf_config_btn":
            self.show_more_information_about_config()
        elif btn == "host_os_btn":
            self.show_os_selector()
        elif btn == "host_platform_btn":
            self.show_platform_os_selector()
        elif btn == "version_btn":
            self.show_version_selector()
        elif btn == "compiler_btn":
            self.show_compiler_selector()
        elif btn == "modules_btn":
            self.show_modules_selector()
        elif btn == "path_btn":
            self._mount_right(PathWidget(self._on_path_done, self.install_config.install_path))
        elif btn == "install_btn":
            self.run_installation()
            return

        self.current_section = event.button.id

    # =========================================================================
    # Разблокировка кнопок
    # =========================================================================

    def _check_and_unlock(self) -> None:
        c = self.install_config
        if c.config_path:
            self.more_inf_config_btn.disabled = False
            self.host_os_btn.disabled = False
        if c.host_os:
            self.host_platform_btn.disabled = False
        if c.platform_host_os:
            self.version_btn.disabled = False
        if c.version:
            self.compiler_btn.disabled = False
        if c.arch:
            self.modules_btn.disabled = False
        if self.modules_done:
            self.path_btn.disabled = False
        if c.install_path:
            self.install_btn.disabled = False

    # =========================================================================
    # Конфиг
    # =========================================================================

    def _mount_right(self, widget) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        right_panel.mount(widget)

    def show_file_picker(self) -> None:
        self._mount_right(ConfigWidget(self._on_config_done))

    def _on_config_done(self, result) -> None:
        if result is None:
            self._show_main_settings()
            return
        config_path, server_results = result
        self.install_config.config_path = config_path
        self._server_results = server_results
        self._versions_cache.clear()
        self._arches_cache.clear()
        self._modules_cache.clear()
        self.update_main_settings()
        self._check_and_unlock()
        self._show_main_settings()
        available = sum(1 for r in server_results if r["status"])
        self.notify(f"Конфиг загружен, доступны {available} из {len(server_results)} серверов")

    def show_more_information_about_config(self) -> None:
        if not self.install_config.config_path:
            self.notify("Конфиг не выбран", severity="warning")
            return
        if not self._server_results:
            self.notify("Проверка серверов ещё не завершена", severity="warning")
            return

        def on_refresh() -> None:
            self._mount_right(ConfigWidget(self._on_config_done, self.install_config.config_path))

        self._mount_right(ConfigDetailsWidget(self._server_results, on_refresh))

    def _show_main_settings(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        right_panel.mount(self.main_settings)
        self.current_section = "main"

    # =========================================================================
    # ОС / Платформа
    # =========================================================================

    def show_os_selector(self) -> None:
        def on_apply(selected: str) -> None:
            self.install_config.host_os = selected
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            self.notify(f"Выбрана ОС: {selected}")

        self._mount_right(RadioSelectorWidget(
            "Выбор операционной системы", self.available_oses, on_apply,
            self.install_config.host_os,
        ))

    def show_platform_os_selector(self) -> None:
        platforms = get_available_platform(self.install_config.host_os)

        def on_apply(selected: str) -> None:
            self.install_config.platform_host_os = selected
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            self.notify(f"Выбрана платформа: {selected}")

        self._mount_right(RadioSelectorWidget(
            "Выбор платформы", platforms, on_apply, self.install_config.platform_host_os,
        ))

    # =========================================================================
    # Версии Qt
    # =========================================================================

    def get_working_urls(self) -> List[str]:
        return [item["url"] for item in self._server_results if item["status"]]

    def show_version_selector(self) -> None:
        c = self.install_config
        if not c.config_path:
            self.notify("Сначала выберите конфиг", severity="warning")
            return
        if not c.host_os or not c.platform_host_os:
            self.notify("Сначала выберите ОС и платформу", severity="warning")
            return

        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов для получения версий", severity="warning")
            return

        cached = self._versions_cache.get((c.host_os, c.platform_host_os))
        self._mount_right(VersionWidget(working_urls, c.host_os, c.platform_host_os,
                                        self._on_version_done, cached_tree=cached))

    def _on_version_done(self, version: Optional[str]) -> None:
        if version is not None:
            self.install_config.version = version
            self.update_main_settings()
            self._check_and_unlock()
            self.notify(f"Выбрана версия Qt: {version}")
        self._show_main_settings()

    # =========================================================================
    # Компилятор / Архитектура
    # =========================================================================

    def show_compiler_selector(self) -> None:
        c = self.install_config
        if not c.config_path:
            self.notify("Сначала выберите конфиг", severity="warning")
            return
        if not all([c.host_os, c.platform_host_os, c.version]):
            self.notify("Сначала выберите ОС, платформу и версию", severity="warning")
            return

        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов для получения списка архитектур", severity="warning")
            return

        cached = self._arches_cache.get((c.host_os, c.platform_host_os, c.version))
        self._mount_right(CompilerWidget(working_urls, c.host_os, c.platform_host_os, c.version,
                                         self._on_compiler_done, cached_arches=cached,
                                         current_arch=c.arch))

    def _on_compiler_done(self, arch: Optional[str]) -> None:
        if arch is not None:
            self.install_config.arch = arch
            self.update_main_settings()
            self._check_and_unlock()
            self.notify(f"Выбран компилятор: {arch}")
        self._show_main_settings()

    # =========================================================================
    # Модули
    # =========================================================================

    def show_modules_selector(self) -> None:
        c = self.install_config
        if not c.config_path:
            self.notify("Сначала выберите конфиг", severity="warning")
            return
        if not all([c.host_os, c.platform_host_os, c.version, c.arch]):
            self.notify("Сначала выберите ОС, платформу, версию и компилятор", severity="warning")
            return

        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов для получения списка модулей", severity="warning")
            return

        cached = self._modules_cache.get((c.host_os, c.platform_host_os, c.version, c.arch))
        self._mount_right(ModulesWidget(working_urls, c.host_os, c.platform_host_os, c.version,
                                        c.arch, self._on_modules_done, cached_modules=cached,
                                        current_modules=c.modules))

    def _on_modules_done(self, modules: Optional[List[str]]) -> None:
        if modules is not None:
            self.install_config.modules = modules
            self.modules_done = True
            self.update_main_settings()
            self._check_and_unlock()
            self.notify(f"Выбрано модулей: {len(modules)}")
        self._show_main_settings()

    # =========================================================================
    # Путь установки
    # =========================================================================

    def _on_path_done(self, path: Optional[Path]) -> None:
        if path is not None:
            self.install_config.install_path = path
            self.update_main_settings()
            self._check_and_unlock()
            self.notify(f"Путь установки: {path}")
        self._show_main_settings()

    # =========================================================================
    # Установка
    # =========================================================================

    def run_installation(self) -> None:
        if not self.install_config.is_valid():
            self.notify("Не все параметры выбраны", severity="warning")
            return

        c = self.install_config
        config_dict = {
            "config_path": str(c.config_path) if c.config_path else None,
            "host_os": c.host_os,
            "platform_host_os": c.platform_host_os,
            "version": c.version,
            "arch": c.arch,
            "modules": c.modules,
            "install_path": str(c.install_path) if c.install_path else None,
            "working_urls": self.get_working_urls(),
        }
        worker_path = str(Path(__file__).parent.parent / "install_worker.py")
        self._mount_right(ProgressWidget(config_dict, worker_path, self._on_install_done))

    def _on_install_done(self, _success: bool) -> None:
        self._show_main_settings()
