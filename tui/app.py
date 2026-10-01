import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Header, Footer, Button, Label, Static

from scan_server.aqt_interface import AqtConfig, get_available_oses, get_available_platform
from tui.sections import (
    SECTIONS, STEPS, build_plan, format_step_value, step_done, version_target,
)
from tui.screens import (
    RadioSelectorWidget,
    ConfigWidget, VersionWidget, CompilerWidget, ModulesWidget, ProgressWidget, PathWidget,
    ToolsWidget, SdeModulesWidget,
    ConfigDetailsWidget,
)


def _detect_host_os() -> str:
    """ОС, на которой запущено приложение, — подставляется в выбор ОС по умолчанию."""
    arm = platform.machine().lower() in ("aarch64", "arm64")
    if sys.platform.startswith("linux"):
        return "linux_arm64" if arm else "linux"
    if sys.platform == "darwin":
        return "mac"
    return "windows_arm64" if arm else "windows"


class AqtTuiApp(App):
    CSS_PATH = ["styles.tcss", "screens/radio_selector.tcss"]

    # --- Разделяемое reactive-состояние ---
    language: reactive[str] = reactive("ru")
    installed_qts: reactive[list] = reactive(list)

    def __init__(self):
        super().__init__()
        self.install_config = AqtConfig()
        self.current_section = "main"   # кнопка, чей виджет сейчас открыт справа
        self._section: Optional[str] = None  # открытый раздел меню; None — главное меню
        self._left_buttons: Dict[str, Button] = {}
        self.available_oses = get_available_oses()

        # Кеш результатов проверки серверов (загружается один раз)
        self._server_results: List[Dict[str, Any]] = []
        self._config_label = ""  # откуда взят конфиг — для сводки

        # Кеш метаданных: ключ — кортеж параметров конфига
        self._versions_cache: Dict = {}   # (host_os, platform) → tree_dict
        self._arches_cache: Dict = {}     # (host_os, platform, version) → list
        self._modules_cache: Dict = {}    # (host_os, platform, version, arch) → module_data
        self._sde_cache: Dict = {}        # (host_os, version, flavor) → list
        self._tools_cache: Dict = {}      # host_os → list

    # =========================================================================
    # Compose
    # =========================================================================

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ScrollableContainer(id="left_panel")
            with Vertical(id="right_panel"):
                self.main_settings = Static(self._format_settings(), id="main_settings")
                yield self.main_settings
        yield Footer()

    def on_mount(self) -> None:
        self._show_menu()

    # =========================================================================
    # Левая панель: главное меню / шаги раздела
    # =========================================================================

    def _show_menu(self) -> None:
        self._section = None
        buttons = [
            Button("Выбрать конфиг", name="config"),
            Button("Подробности конфига", name="config_details"),
            Label("Что установить", classes="menu-caption"),
        ]
        buttons += [Button(title, name=f"section:{key}") for key, (title, _, _) in SECTIONS.items()]
        self._rebuild_left(buttons)

    def _open_section(self, section: str) -> None:
        self._section = section
        _, steps, _ = SECTIONS[section]
        buttons = [Button("← Главное меню", name="back")]
        buttons += [Button(f"{i}. {STEPS[step][0]}", name=f"step:{step}") for i, step in enumerate(steps, 1)]
        buttons.append(Button("Установить", name="install", variant="success"))
        self._rebuild_left(buttons)

    def _rebuild_left(self, widgets: list) -> None:
        left_panel = self.query_one("#left_panel")
        left_panel.remove_children()
        left_panel.mount_all(widgets)
        self._left_buttons = {w.name: w for w in widgets if isinstance(w, Button)}
        self._refresh_left()
        self.call_after_refresh(widgets[0].focus)
        self._show_main_settings()

    def _is_enabled(self, name: str) -> bool:
        c = self.install_config
        if name in ("config", "back"):
            return True
        if name == "config_details" or name.startswith("section:"):
            return bool(c.config_path)
        _, steps, _ = SECTIONS[self._section]
        if name == "install":
            return all(step_done(s, c) for s in steps)
        step = name.removeprefix("step:")
        # шаг доступен, когда пройдены все предыдущие
        return all(step_done(s, c) for s in steps[:steps.index(step)])

    def _refresh_left(self) -> None:
        for name, button in self._left_buttons.items():
            button.disabled = not self._is_enabled(name)

    # =========================================================================
    # Сводка (правая панель по умолчанию)
    # =========================================================================

    def _format_settings(self) -> str:
        c = self.install_config
        config_line = f"Конфиг: {self._config_label or c.config_path or 'не выбран'}"
        if self._section is None:
            if not c.config_path:
                return f"{config_line}\n\nНажмите «Выбрать конфиг», чтобы начать."
            available = sum(1 for r in self._server_results if r["status"])
            return (f"{config_line}\nДоступно серверов: {available} из {len(self._server_results)}\n\n"
                    "Выберите в меню слева, что установить.")

        title, steps, contents = SECTIONS[self._section]
        lines = [f"Раздел: {title}", f"Будет установлено: {contents}", config_line, ""]
        lines += [f"{STEPS[step][1]}: {format_step_value(step, c)}" for step in steps]
        return "\n".join(lines)

    def update_main_settings(self) -> None:
        self.main_settings.update(self._format_settings())

    # =========================================================================
    # Обработчик кнопок
    # =========================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name
        if name is None:
            return  # кнопки внутри виджетов правой панели обрабатываются самими виджетами

        if self.current_section != "main" and name == self.current_section:
            self._show_main_settings()
            return

        if name == "back":
            self._show_menu()
            return
        if name.startswith("section:"):
            self._open_section(name.removeprefix("section:"))
            return
        if name == "install":
            self.run_installation()
            return

        if name == "config":
            self.show_file_picker()
        elif name == "config_details":
            self.show_more_information_about_config()
        elif name.startswith("step:"):
            self._show_step(name.removeprefix("step:"))

        self.current_section = name

    # =========================================================================
    # Правая панель
    # =========================================================================

    def _mount_right(self, widget) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        right_panel.mount(widget)

    def _show_main_settings(self) -> None:
        self.update_main_settings()
        self._mount_right(self.main_settings)
        self.current_section = "main"

    def _apply_step(self, step: str, field: str, value: Any) -> None:
        """Общий коллбэк шагов: None — отмена/ошибка, иначе сохранить значение."""
        if value is not None:
            self.install_config.set(field, value)
            self._refresh_left()
            self.notify(f"{STEPS[step][1]}: {format_step_value(step, self.install_config)}")
        self._show_main_settings()

    # =========================================================================
    # Конфиг
    # =========================================================================

    def show_file_picker(self) -> None:
        self._mount_right(ConfigWidget(self._on_config_done))

    def _on_config_done(self, result) -> None:
        if result is None:
            self._show_main_settings()
            return
        config_path, server_results, label = result
        if config_path != self.install_config.config_path:
            self._versions_cache.clear()
            self._arches_cache.clear()
            self._modules_cache.clear()
            self._sde_cache.clear()
            self._tools_cache.clear()
        self.install_config.config_path = config_path
        self._server_results = server_results
        self._config_label = label
        self._refresh_left()
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
            self._mount_right(ConfigWidget(self._on_config_done, self.install_config.config_path,
                                           self._config_label))

        self._mount_right(ConfigDetailsWidget(self._server_results, on_refresh))

    def get_working_urls(self) -> List[str]:
        return [item["url"] for item in self._server_results if item["status"]]

    # =========================================================================
    # Шаги разделов
    # =========================================================================

    def _show_step(self, step: str) -> None:
        c = self.install_config
        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов, проверьте конфиг", severity="warning")
            return

        def done(field: str):
            return lambda value: self._apply_step(step, field, value)

        if step == "host_os":
            # all_os (wasm и т.п.) — только для Qt: инструментов и документации под него нет
            oses = [o for o in self.available_oses if o != "all_os" or self._section == "qt"]
            self._mount_right(RadioSelectorWidget(
                "Выбор операционной системы", oses, done("host_os"), c.host_os or _detect_host_os(),
            ))
        elif step == "platform":
            self._mount_right(RadioSelectorWidget(
                "Выбор платформы", get_available_platform(c.host_os), done("platform_host_os"),
                c.platform_host_os,
            ))
        elif step == "version":
            target = version_target(self._section, c)
            self._mount_right(VersionWidget(
                working_urls, c.host_os, target, done("version"),
                cached_tree=self._versions_cache.get((c.host_os, target)), config_path=c.config_path,
            ))
        elif step == "arch":
            self._mount_right(CompilerWidget(
                working_urls, c.host_os, c.platform_host_os, c.version, done("arch"),
                cached_arches=self._arches_cache.get((c.host_os, c.platform_host_os, c.version)),
                current_arch=c.arch, config_path=c.config_path,
            ))
        elif step == "modules":
            self._mount_right(ModulesWidget(
                working_urls, c.host_os, c.platform_host_os, c.version, c.arch, done("modules"),
                cached_modules=self._modules_cache.get((c.host_os, c.platform_host_os, c.version, c.arch)),
                current_modules=c.modules, config_path=c.config_path,
            ))
        elif step in ("doc_modules", "example_modules"):
            flavor = "doc" if step == "doc_modules" else "examples"
            self._mount_right(SdeModulesWidget(
                working_urls, c.host_os, c.version, flavor, done(step),
                cached_modules=self._sde_cache.get((c.host_os, c.version, flavor)),
                current_modules=getattr(c, step), config_path=c.config_path,
            ))
        elif step == "tools":
            self._mount_right(ToolsWidget(
                working_urls, c.host_os, done("tools"),
                cached_tools=self._tools_cache.get(c.host_os), current_tools=c.tools,
                config_path=c.config_path,
            ))
        elif step == "path":
            self._mount_right(PathWidget(done("install_path"), c.install_path))

    # =========================================================================
    # Установка
    # =========================================================================

    def run_installation(self) -> None:
        if self._section is None or not self._is_enabled("install"):
            self.notify("Не все параметры выбраны", severity="warning")
            return

        c = self.install_config
        config_dict = {
            "config_path": str(c.config_path) if c.config_path else None,
            "host_os": c.host_os,
            "platform_host_os": c.platform_host_os,
            "version": c.version,
            "arch": c.arch,
            "modules": c.modules or [],
            "install_path": str(c.install_path) if c.install_path else None,
            "working_urls": self.get_working_urls(),
            "plan": build_plan(self._section, c),
        }
        worker_path = str(Path(__file__).parent.parent / "install_worker.py")
        title = SECTIONS[self._section][0]
        self._mount_right(ProgressWidget(config_dict, worker_path, self._on_install_done, title))
        self.current_section = "install"

    def _on_install_done(self, _success: bool) -> None:
        self._show_main_settings()
