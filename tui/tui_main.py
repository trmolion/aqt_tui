import os
import logging
import queue
import subprocess
import json
import sys
import tempfile
import threading

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, DirectoryTree, Static, RadioSet, RadioButton, DataTable, ProgressBar, Label, Tree, Checkbox, Input, RichLog
from textual.coordinate import Coordinate
from textual import work
from pathlib import Path
from typing import Dict, List, Any

from scan_server.aqt_interface import AqtConfig, get_available_oses, get_available_platform, get_versions_tree_with_config, get_available_architectures, get_available_modules, run_installation_with_urls
from scan_server.check_servers import get_urls_from_config, check_single_server

class Aqt_tui_installer(App):
    CSS_PATH = "styles.tcss"


    def __init__(self):
        super().__init__()
        self.config = AqtConfig()
        self.current_section = "main"
        self.available_oses = get_available_oses()   # список строк: 'windows', 'linux', 'mac'
        self.avaliable_os_platform = []
        
        self._sort_reverse = False
        self._last_sort_column = None
        
        self.install_path = None
        self.install_path_label = None
        self.folder_name_input = None


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
        elif event.button.id == "os_done_btn":
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
        elif event.button.id == "compiler_btn":
            self.show_compiler_selector()
        elif event.button.id == "compiler_done_btn":
            radio_set = self.query_one("#compiler_radio")
            selected = None
            for btn in radio_set.query(RadioButton):
                if btn.value:
                    selected = btn.id
                    break
            if selected:
                self.config.arch = selected
                self.update_main_settings()
                self._check_and_unlock()
                self._show_main_settings()
                self.notify(f"Выбран компилятор: {selected}")
            else:
                self.notify("Выберите компилятор", severity="warning")
        elif event.button.id == "modules_btn":
            self.show_modules_selector()
        elif event.button.id == "select_all_modules":
            table = self.query_one("#modules_table")
            col_index = table.get_column_index("select")
            for row_index in range(len(table.rows)):
                table.update_cell_at(Coordinate(row_index, col_index), "☑")
        elif event.button.id == "modules_done_btn":
            table = self.query_one("#modules_table")
            col_index = table.get_column_index("select")
            selected = []
            for row_index, row_key in enumerate(table.rows):
                row = table.get_row(row_key)
                if row[col_index] == "☑":
                    module_name = row[1]  # вторая колонка
                    selected.append(module_name)
            self.config.modules = selected
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            self.notify(f"Выбрано модулей: {len(selected)}")
        elif event.button.id == "path_btn":
            self.select_path_install()
        elif event.button.id == "accept_path_btn":
            if self.install_path is None:
                self.notify("Сначала выберите путь в дереве", severity="warning")
                return
            # Если чекбокс выбран, добавляем имя папки
            make_dir_check = self.query_one("#make_dir_check")
            if make_dir_check.value:
                folder_name = self.query_one("#folder_name_input").value.strip()
                if not folder_name:
                    self.notify("Введите имя папки", severity="warning")
                    return
                final_path = self.install_path / folder_name
            else:
                final_path = self.install_path
            self.config.install_path = final_path
            self.update_main_settings()
            self._check_and_unlock()
            self._show_main_settings()
            self.notify(f"Путь установки: {final_path}")
        elif event.button.id == "install_btn":
            self.run_installation()
            
        self.current_section = event.button.id



    def _check_and_unlock(self) -> None:
        if self.config.config_path:
            self.more_inf_config_btn.disabled = False
            self.host_os_btn.disabled = False
        if self.config.host_os:
            self.host_platform_btn.disabled = False
        if self.config.platform_host_os:
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



    def show_progress_indicator(self, message: str, total: int = None, pulsing: bool = False) -> None:
        """Показывает индикатор прогресса в правой панели."""
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        container = Vertical(id="progress_container")
        right_panel.mount(container)
        container.mount(Label(message))
        
        if pulsing:
            # Пульсирующий прогресс-бар (неопределённый)
            self.progress_bar = ProgressBar(total=100, show_eta=False)
            self.progress_bar.advance(50)  # начальная позиция
            container.mount(self.progress_bar)
            # Запускаем анимацию пульсации (можно через реактивный стиль, но проще так)
            self.set_timer(0.1, self._pulse_progress)
        else:
            self.progress_bar = ProgressBar(total=total or 100, show_eta=False)
            container.mount(self.progress_bar)

    def _pulse_progress(self) -> None:
        """Анимирует пульсацию прогресс-бара."""
        if hasattr(self, 'progress_bar') and self.progress_bar.total is not None:
            current = self.progress_bar.progress
            if current >= 90:
                self.progress_bar.advance(-80)
            else:
                self.progress_bar.advance(10)
            self.set_timer(0.2, self._pulse_progress)



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
        if self.current_section == "config_btn":
            path = event.path
            if path.suffix == ".ini":
                self.start_config_verification(path)
            else:
                self.notify("Выберите файл .ini", severity="warning")


    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        if self.current_section == "path_btn":
            self.install_path = event.path
            self.notify(f"Выбран путь: {self.install_path}")
            # Обновляем label
            if self.install_path_label:
                self.install_path_label.update(f"Выбран путь: {self.install_path}")
            
        
    
    
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
        scrl_cnt = ScrollableContainer()
        right_panel.mount(scrl_cnt)
        refresh_btn = Button("Обновить проверку", id="refresh_config_check")
        scrl_cnt.mount(Static("\n".join(lines), id="config_details"))
        scrl_cnt.mount(refresh_btn)
        
        
        
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
        


    # === Выбор версий Qt ===
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



    # === Выбор версий компилятора для конкретной версии
    def show_compiler_selector(self) -> None:
        if not self.config.config_path:
            self.notify("Сначала выберите конфиг", severity="warning")
            return
        if not self.config.host_os or not self.config.platform_host_os or not self.config.version:
            self.notify("Сначала выберите ОС, платформу и версию", severity="warning")
            return

        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов для получения списка архитектур", severity="warning")
            return

        try:
            arches = get_available_architectures(
                working_urls,
                self.config.host_os,
                self.config.platform_host_os,
                self.config.version
            )
            if not arches:
                self.notify("Нет доступных архитектур для выбранной версии", severity="warning")
                return
        except Exception as e:
            self.notify(f"Ошибка получения архитектур: {e}", severity="error")
            return

        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()

        # Создаём радиокнопки для каждой архитектуры
        buttons = [RadioButton(arch, id=arch) for arch in arches]
        radio_set = RadioSet(*buttons, id="compiler_radio")
        right_panel.mount(radio_set)
        done_btn = Button("Применить", id="compiler_done_btn")
        right_panel.mount(done_btn)
        
        
    def show_modules_selector(self) -> None:
        if not self.config.config_path:
            self.notify("Сначала выберите конфиг", severity="warning")
            return
        if not all([self.config.host_os, self.config.platform_host_os, self.config.version, self.config.arch]):
            self.notify("Сначала выберите ОС, платформу, версию и компилятор", severity="warning")
            return

        working_urls = self.get_working_urls()
        if not working_urls:
            self.notify("Нет доступных серверов для получения списка модулей", severity="warning")
            return

        try:
            module_data = get_available_modules(
                working_urls,
                self.config.host_os,
                self.config.platform_host_os,
                self.config.version,
                self.config.arch
            )
            if not module_data:
                self.notify("Нет доступных модулей для выбранной конфигурации", severity="warning")
                return
        except Exception as e:
            self.notify(f"Ошибка получения модулей: {e}", severity="error")
            return

        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()

        # Создаём таблицу
        table = DataTable(id="modules_table")
        table.add_columns(
            ("Выбрать", "select"),
            ("Модуль", "module"),
            ("Описание", "description"),
            ("Дата релиза", "release_date"),
            ("Размер загрузки", "compressed_size"),
            ("Размер установки", "uncompressed_size")
        )
        table.cursor_type = "row"

        # Заполняем строки
        for module_name, info in module_data.table_data.items():
            display_name = info.get("DisplayName", "")
            release_date = info.get("ReleaseDate", "")
            compressed = info.get("CompressedSize", "")
            uncompressed = info.get("UncompressedSize", "")
            table.add_row("☐", module_name, display_name, release_date, compressed, uncompressed, key=module_name)

        # Кнопки
        select_all_btn = Button("Выбрать всё", id="select_all_modules")
        done_btn = Button("Применить", id="modules_done_btn")

        # Монтируем всё в right_panel
        podlojka = ScrollableContainer()
        right_panel.mount(podlojka)
        
        podlojka.mount(table)
        podlojka.mount(select_all_btn)
        podlojka.mount(done_btn)
        
        def sort_key(row_tuple):
            # row_tuple — это кортеж значений строки: (select, module, description, release_date, compressed, uncompressed)
            size_str = row_tuple[4]  # колонка "Размер загрузки" на позиции 4
            return self._parse_size(size_str)
        # Сортируем строки по убыванию (reverse=True)
        table.sort(key=sort_key, reverse=True)

        table.focus()
            
        
        
    def on_data_table_row_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table.id == "modules_table":
            table = event.data_table
            row_index = event.cursor_row
            col_index = table.get_column_index("select")
            current = table.get_row_at(row_index)[col_index]
            new_state = "☑" if current == "☐" else "☐"
            table.update_cell_at(Coordinate(row_index, col_index), new_state)
            
            
    def _parse_size(self, size_str: str) -> float:
        """Преобразует строку размера (например, '113.2M', '468.5M') в число (байты)."""
        if not size_str:
            return 0
        size_str = size_str.strip().upper()
        multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
        if size_str[-1] in multipliers:
            num = float(size_str[:-1])
            return num * multipliers[size_str[-1]]
        else:
            # Предполагаем, что число в байтах
            return float(size_str)
        
        
        
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "modules_table":
            return
        
        table = event.data_table
        column_key = event.column_key
        
        # Сортируем только по колонкам размера
        if column_key in ("compressed_size", "uncompressed_size"):
            # Меняем направление сортировки при повторном клике
            if hasattr(self, '_last_sort_column') and self._last_sort_column == column_key:
                self._sort_reverse = not getattr(self, '_sort_reverse', False)
            else:
                self._sort_reverse = False
            self._last_sort_column = column_key
            
            # Сортируем, указывая колонку и key-функцию для одного значения
            table.sort(column_key, key=self._parse_size, reverse=self._sort_reverse)
            
            
            
    def select_path_install(self) -> None:
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()
        
        # Label для отображения текущего пути
        str_lbl = self.install_path if self.install_path is not None else "Путь не выбран"
        path_label = Label(str_lbl, id="install_path_label")
        right_panel.mount(path_label)
        self.install_path_label = path_label
        
        # Checkbox
        make_dir_check = Checkbox("Создавать папку", id="make_dir_check")
        right_panel.mount(make_dir_check)
        
        # Input для имени папки (изначально скрыт)
        folder_input = Input(placeholder="Имя папки", id="folder_name_input")
        folder_input.styles.display = "none"
        right_panel.mount(folder_input)
        self.folder_name_input = folder_input
        
        # Кнопка "Принять путь"
        accept_btn = Button("Принять путь", id="accept_path_btn")
        right_panel.mount(accept_btn)
        
        # DirectoryTree
        tree = DirectoryTree(Path.home())
        right_panel.mount(tree)
        tree.focus()
    
    
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "make_dir_check":
            folder_input = self.query_one("#folder_name_input")
            if event.value:
                folder_input.styles.display = "block"
                folder_input.focus()
            else:
                folder_input.styles.display = "none"
                folder_input.value = ""  # очищаем ввод
                
                
                
    def run_installation(self) -> None:
        """Запускает установку в отдельном процессе и читает вывод в реальном времени."""
        if not self.config.is_valid():
            self.notify("Не все параметры выбраны", severity="warning")
            return

        # Подготавливаем UI
        self.setup_logging_ui()

        # Сериализуем конфигурацию во временный JSON
        config_dict = {
            'config_path': str(self.config.config_path) if self.config.config_path else None,
            'host_os': self.config.host_os,
            'platform_host_os': self.config.platform_host_os,
            'version': self.config.version,
            'arch': self.config.arch,
            'modules': self.config.modules,
            'install_path': str(self.config.install_path) if self.config.install_path else None,
            'working_urls': self.get_working_urls(),
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_dict, f)
            self.config_json_path = f.name

        # Запускаем подпроцесс с захватом stdout
        self.install_process = subprocess.Popen(
            [sys.executable, "install_worker.py", self.config_json_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            start_new_session=True
        )

        self.log_queue = queue.Queue()
        self.stop_reading = False

        # Поток для чтения вывода процесса
        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()

        # Таймер для обработки очереди в главном потоке
        self._log_timer = self.set_interval(0.05, self._process_log_queue)
        # Таймер для проверки завершения процесса
        self._completion_timer = self.set_interval(0.2, self._check_process_completion)

    def _read_process_output(self):
        """Читает stdout процесса и кладёт строки в очередь."""
        try:
            for line in iter(self.install_process.stdout.readline, ''):
                if self.stop_reading:
                    break
                self.log_queue.put(line)
        except Exception as e:
            self.log_queue.put(f"ERROR reading output: {e}\n")
        finally:
            self.log_queue.put(None)  # сигнал завершения

    def _process_log_queue(self):
        """Обрабатывает накопившиеся строки из очереди в главном потоке."""
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line is None:
                    self._log_timer.stop()
                    break
                self._handle_log_line(line)
        except queue.Empty:
            pass

    def _handle_log_line(self, line: str):
        """Обрабатывает одну строку лога."""
        clean = line.strip()
        if clean:
            self.rich_log.write(clean)
            # Обновление прогресса
            if "Downloading" in clean or "Extracting" in clean or "Finished" in clean:
                if hasattr(self, 'install_progress') and self.install_progress.total:
                    if self.install_progress.progress < self.install_progress.total:
                        self.install_progress.advance(1)
            # Установка общего количества пакетов
            if "===TOTAL_PACKAGES:" in clean:
                try:
                    total_pkgs = int(clean.split(":")[1].replace("===", ""))
                    self.install_progress.total = total_pkgs * 2
                    self.install_progress.update(progress=0)
                except ValueError:
                    pass

    def _check_process_completion(self):
        """Проверяет, завершился ли процесс."""
        if self.install_process.poll() is not None:
            self._completion_timer.stop()
            self.set_timer(0.5, self._finish_installation)

    def _finish_installation(self):
        """Завершает установку, останавливает таймеры и закрывает ресурсы."""
        self.stop_reading = True
        if hasattr(self, '_log_timer'):
            self._log_timer.stop()
        if self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1.0)
        self.install_process.stdout.close()
        exit_code = self.install_process.wait()
        success = (exit_code == 0)
        # Удаляем временный JSON-файл
        try:
            os.unlink(self.config_json_path)
        except OSError:
            pass
        self.on_installation_done(success, None if success else f"Процесс завершился с кодом {exit_code}")
        
        
    def setup_logging_ui(self) -> None:
        """Перестраивает правую панель под окно установки."""
        right_panel = self.query_one("#right_panel")
        right_panel.remove_children()

        self.install_progress = ProgressBar(total=100, show_eta=True)
        self.rich_log = RichLog(highlight=True, markup=False, wrap=True)

        right_panel.mount(
            Label("Установка Qt... ", classes="title-label"),
            self.install_progress,
            self.rich_log
        )
        
        
    def on_installation_done(self, success: bool, error_msg: str = None) -> None:
        """Вызывается после завершения установки."""
        # Очищаем таймеры
        if hasattr(self, '_log_timer'):
            self._log_timer.stop()
        if hasattr(self, '_completion_timer'):
            self._completion_timer.stop()

        if success:
            self.rich_log.write("\n[green]Установка успешно завершена![/]")
            self.notify("Установка Qt завершена успешно", severity="information")
        else:
            self.rich_log.write(f"\n[red]Ошибка установки: {error_msg}[/]")
            self.notify(f"Ошибка установки: {error_msg}", severity="error")

        # Возвращаем основную панель настроек через 2 секунды
        self.set_timer(2.0, self._show_main_settings)    