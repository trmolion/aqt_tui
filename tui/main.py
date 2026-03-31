from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Button, DirectoryTree, Static, RadioSet, RadioButton, Select, ProgressBar, Label, Tree
from textual import work
from pathlib import Path
from typing import Optional, Dict, List, Any

from scan_server.aqt_interface import AqtConfig, get_available_oses, get_available_platform, get_versions_tree_with_config
from scan_server.check_servers import get_urls_from_config, check_single_server

class Aqt_tui_installer(App):
    CSS_PATH = "styles.tcss"


    def __init__(self):
        super().__init__()
        self.config = AqtConfig()
        self.current_section = "main"
        self.available_oses = get_available_oses()   # список строк: 'windows', 'linux', 'mac'
        self.avaliable_os_platform = []



    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left_panel"):
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



    def _format_settings(self) -> str:
        lines = []
        config_str = str(self.config.config_path) if self.config.config_path else "не выбран"
        lines.append(f"Конфиг: {config_str}")
        os_str = self.config.host_os if self.config.host_os else "не выбрана"
        lines.append(f"ОС: {os_str}")
        target_str = self.config.platform_host_os if self.config.platform_host_os else "не выбрана"
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
        if (self.current_section != "main" and event.button.id == self.current_section):
            self._show_main_settings()
            return

        if event.button.id == "config_btn":
            self.show_file_picker()
        if event.button.id == "more_inf_config_btn":
            self.show_more_information_about_config()
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
        elif event.button.id == "host_platform_btn":
            self.show_platform_os_selector()
        elif event.button.id == "platform_os_done_btn":
            if self.config.platform_host_os:
                self.update_main_settings()
                self._check_and_unlock()
                self._show_main_settings()
                self.notify(f"Выбрана платформа: {self.config.platform_host_os}")
            else:
                self.notify("Выберите платформу ОС", severity="warning")
        elif event.button.id == "refresh_config_check":
            self.start_config_verification(self.config.config_path)
        elif event.button.id == "version_btn":
            self.show_version_selector()
            
        self.current_section = event.button.id



    def _check_and_unlock(self) -> None:
        if self.config.config_path:
            self.more_inf_config_btn.disabled = False
            self.host_os_btn.disabled = False
        if self.config.host_os:
            self.host_platform_btn.disabled = False
        if self.config.platform_host_os:
            self.version_btn.disabled = False
        if self.config.version:          # добавлено
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



    def start_config_verification(self, config_path: Path) -> None:
        """Запускает проверку конфига с отображением прогресса."""
        self.config.config_path = config_path
        # Получаем общее количество URL для прогресса
        urls = get_urls_from_config(config_path)
        self.show_progress_indicator("Проверка серверов...", total=len(urls))
        self.verify_config_worker(urls, config_path)



    @work(thread=True)
    def verify_config_worker(self, urls, config_path: Path) -> None:
        """Фоновая проверка серверов с обновлением прогресса."""
        # urls = get_urls_from_config(config_path)
        total = len(urls)
        results = []
        for i, url in enumerate(urls):
            # Проверяем один URL
            result = check_single_server(url)
            results.append(result)
            # Обновляем прогресс
            self.call_from_thread(self.update_progress, i + 1, total, url)
        self.call_from_thread(self.on_config_verification_done, results)



    def update_progress(self, current: int, total: int, current_url: str = None) -> None:
        if hasattr(self, 'progress_bar'):
            self.progress_bar.update(progress=current, total=total)
        if current_url:
            self.query_one("#progress_container Label").update(f"Проверка серверов... ({current}/{total})   Сервер: {current_url}")



    def show_progress_indicator(self, message: str, total: int) -> None:
        """Показывает индикатор прогресса в правой панели с заданным total."""
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        container = Vertical(id="progress_container")
        right_panel.mount(container)
        container.mount(Label(message))
        # Создаём прогресс-бар с заданным total
        self.progress_bar = ProgressBar(total=total, show_eta=False)
        container.mount(self.progress_bar)



    def on_config_verification_done(self, results: List[Dict[str, Any]]) -> None:
        self.config_servers_details = results
        any_ok = any(r['status'] for r in results)
        if any_ok:
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            available = sum(1 for r in results if r['status'])
            self.notify(f"Конфиг загружен, доступны {available} из {len(results)} серверов")
        else:
            self.config.config_path = None
            self._show_main_settings()
            self.notify("Не удалось подключиться ни к одному серверу", severity="error")
    
    
        
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path
        if path.suffix == ".ini":
            self.start_config_verification(path)
        else:
            self.notify("Выберите файл .ini", severity="warning")
    
    
    
    def show_more_information_about_config(self) -> None:
        if not self.config.config_path:
            self.notify("Конфиг не выбран", severity="warning")
            return
        if not self.config_servers_details:
            self.notify("Проверка серверов ещё не завершена", severity="warning")
            return

        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()

        lines = ["[bold]Результаты проверки серверов:[/]"]
        lines.append("")
        for item in self.config_servers_details:
            url = item['url']
            status = item['status']
            status_code = item['status_code']
            resp_time = item['response_time']
            error = item['error']

            if status:
                status_icon = "[green]●[/]"
                time_str = f"{resp_time:.3f} с"
            else:
                status_icon = "[red]●[/]"
                time_str = f"{resp_time:.3f} с" if resp_time is not None else "—"

            lines.append(f"{status_icon} {url}")
            lines.append(f"\tВремя ответа: {time_str}")
            lines.append(f"\tКод ответа: {status_code}")
            if error:
                lines.append(f"   Ошибка: {error}")
            lines.append("")

        # Кнопка обновления
        refresh_btn = Button("Обновить проверку", id="refresh_config_check")
        right_panel.mount(Static("\n".join(lines), id="config_details"))
        right_panel.mount(refresh_btn)
        
        
    def _show_main_settings(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        right_panel.mount(self.main_settings)
        self.current_section = "main"



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
        """Сохраняем выбор на radioButton (id кнопки = имя настройки)"""
        if event.radio_set.id == "os_radio":
            self.config.host_os = event.pressed.id
        elif event.radio_set.id == "os_platform_radio":
            self.config.platform_host_os = event.pressed.id
    
    
    
    # === Выбор платформы ОС ===
    def show_platform_os_selector(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        # Записываем доступные платформы под ОС
        self.avaliable_os_platform = get_available_platform(self.config.host_os)
        # Создаём радиокнопки с id, равным имени платформы под ОС
        buttons = [RadioButton(os_platform_name.capitalize(), id=os_platform_name) for os_platform_name in self.avaliable_os_platform]
        radio_set = RadioSet(*buttons, id="os_platform_radio")
        right_panel.mount(radio_set)
        done_btn = Button("Применить", id="platform_os_done_btn")
        right_panel.mount(done_btn)



    def on_radio_set_changed_platform(self, event: RadioSet.Changed) -> None:
        """Сохраняем выбранную платформу ОС"""
        self.config.platform_host_os = event.pressed.id
        
    
    
    def get_working_urls(self) -> List[str]:
        if not self.config_servers_details:
            return []
        return [item['url'] for item in self.config_servers_details if item['status']]
        


    def show_version_selector(self) -> None:
        if not self.config.config_path:
            self.notify("Сначала выберите конфиг", severity="warning")
            return
        if not self.config.host_os or not self.config.platform_host_os:
            self.notify("Сначала выберите ОС и платформу", severity="warning")
            return

        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов для получения версий", severity="warning")
            return

        try:
            tree_dict = get_versions_tree_with_config(
                working_urls,
                self.config.host_os,
                self.config.platform_host_os
            )
            if not tree_dict:
                self.notify("Нет доступных версий для выбранной конфигурации", severity="warning")
                return
        except Exception as e:
            self.notify(f"Ошибка получения версий: {e}", severity="error")
            return

        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()

        tree = Tree("Версии Qt", id="version_tree")
        tree.root.expand()
        for major, versions in sorted(tree_dict.items(), reverse=True):
            node = tree.root.add(str(major), expand=True)
            for version in versions:
                node.add_leaf(version)

        right_panel.mount(tree)
        tree.focus()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Обработка выбора версии в дереве."""
        if event.node.is_root:
            return
        # Если узел — лист (версия), сохраняем
        if not event.node.children:
            selected_version = event.node.label.plain
            self.config.version = selected_version
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            self.notify(f"Выбрана версия Qt: {selected_version}")
        else:
            # Если узел — мажорная версия, просто раскрываем/закрываем, не сохраняем
            event.node.toggle()
