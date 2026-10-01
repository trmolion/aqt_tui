"""Утилиты для работы с aqtinstaller."""
import logging
import os
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import aqt
from aqt.archives import QtArchives
from aqt.helper import MyConfigParser, Settings
from aqt.installer import run_installer
from aqt.metadata import ArchiveId, MetadataFactory, Version, ModuleData


# settings.ini, который aqt читает по умолчанию
_AQT_DEFAULT_INI = Path(aqt.__file__).parent / "settings.ini"

# Settings в aqt — глобальный объект (Borg). Воркеры TUI работают в разных потоках,
# поэтому подменять его конфиг можно только по очереди.
_settings_lock = threading.Lock()


class AqtConfig:
    """Хранит и управляет настройками установки Qt."""
    def __init__(self):
        self.config_path: Optional[Path] = None     # путь с конфигом для установки
        self.host_os: Optional[str] = None          # 'windows', 'linux', 'mac'
        self.platform_host_os: Optional[str] = None # под какой компилятор Qt
        self.version: Optional[str] = None          # версия qt
        self.arch: Optional[str] = None             # компилятор, архитектура
        self.modules: List[str] = []                # список модулей
        self.install_path: Optional[Path] = None    # путь установки qt

    def is_valid(self) -> bool:
        """Проверяет, заполнены ли все обязательные поля."""
        return all([
            self.config_path,
            self.host_os,
            self.platform_host_os,
            self.version,
            self.arch,
            self.install_path
        ])


# =============================================================================
# Настройки aqt
# =============================================================================

def _build_aqt_config(urls: List[str], config_path: Optional[Path]) -> MyConfigParser:
    """
    Собирает конфиг aqt: настройки по умолчанию + пользовательский .ini + проверенные зеркала.
    Первый URL становится baseurl, остальные — fallbacks. Источники хешей (trusted_mirrors)
    и INSECURE_NOT_FOR_PRODUCTION_ignore_hash берутся из .ini как есть — проверку хешей
    можно отключить только явно в конфиге.
    """
    if not urls:
        raise ValueError("No URLs provided")

    parser = MyConfigParser()
    parser.read(_AQT_DEFAULT_INI, encoding="utf-8")
    if config_path:
        with open(config_path, encoding="utf-8") as f:
            parser.read_file(f)

    for section in ("aqt", "mirrors"):
        if not parser.has_section(section):
            parser.add_section(section)
    parser.set("aqt", "baseurl", urls[0])
    # aqt делает random.choice(fallbacks), поэтому пустой список недопустим
    parser.set("mirrors", "fallbacks", "\n".join(urls[1:] or urls[:1]))
    return parser


@contextmanager
def _aqt_settings(urls: List[str], config_path: Optional[Path]) -> Iterator[MyConfigParser]:
    """Временно подменяет конфиг aqt на собранный из urls и config_path."""
    config = _build_aqt_config(urls, config_path)
    with _settings_lock:
        old_config = Settings.config
        Settings.config = config
        try:
            yield config
        finally:
            Settings.config = old_config


# =============================================================================
# Метаданные
# =============================================================================

def get_available_oses() -> List[str]:
    """Возвращает список поддерживаемых операционных систем."""
    return list(ArchiveId.TARGETS_FOR_HOST.keys())


def get_available_platform(host_os: str) -> List[str]:
    """Возвращает доступные целевые платформы для заданной ОС."""
    return list(ArchiveId.TARGETS_FOR_HOST[host_os])


def get_versions_tree_with_config(
    urls: List[str], host_os: str, target: str, config_path: Optional[Path] = None,
) -> Dict[int, List[str]]:
    """
    Возвращает дерево версий Qt, используя переданные серверы.
    Первый URL в списке используется как baseurl, остальные как fallbacks.
    """
    with _aqt_settings(urls, config_path):
        meta = MetadataFactory(ArchiveId("qt", host_os, target), base_url=urls[0])
        versions = meta.fetch_versions().flattened()

    tree = {}
    for ver in versions:
        tree.setdefault(ver.major, []).append(str(ver))
    for major in tree:
        tree[major].sort(key=lambda v: Version(v))
    return tree


def get_available_architectures(
    urls: List[str], host_os: str, target: str, version: str, config_path: Optional[Path] = None,
) -> List[str]:
    """
    Возвращает список доступных архитектур для заданной версии Qt,
    используя переданные серверы.
    """
    try:
        version_obj = Version(version)
    except ValueError as e:
        raise ValueError(f"Invalid version string: {version}") from e

    with _aqt_settings(urls, config_path):
        meta = MetadataFactory(ArchiveId("qt", host_os, target), base_url=urls[0])
        arches = meta.fetch_arches(version_obj)
    return arches if isinstance(arches, list) else []


def get_available_modules(
    urls: List[str], host_os: str, target: str, version: str, arch: str,
    config_path: Optional[Path] = None,
) -> ModuleData:
    """
    Возвращает список доступных модулей для заданной версии и архитектуры Qt,
    используя переданные серверы.
    """
    try:
        version_obj = Version(version)
    except ValueError as e:
        raise ValueError(f"Invalid version string: {version}") from e

    with _aqt_settings(urls, config_path):
        meta = MetadataFactory(ArchiveId("qt", host_os, target), base_url=urls[0])
        return meta.fetch_long_modules(version_obj, arch)


# =============================================================================
# Установка
# =============================================================================

def run_installation_with_urls(config: AqtConfig, urls: List[str]) -> None:
    """
    Устанавливает Qt, используя переданные серверы.
    """
    # --- ПЕРЕНАСТРОЙКА ЛОГГЕРА AQT ---
    if config.install_path:
        log_path = config.install_path / "aqtinstall.log"
        # Получаем логгер aqt
        aqt_logger = logging.getLogger("aqt")
        # Удаляем все старые обработчики
        for handler in aqt_logger.handlers[:]:
            aqt_logger.removeHandler(handler)
        # Добавляем обработчик в нужный файл
        file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        aqt_logger.addHandler(file_handler)
        aqt_logger.setLevel(logging.DEBUG)
        # Не забываем также установить Settings.logfile для совместимости
        Settings.logfile = log_path
    # --- КОНЕЦ ПЕРЕНАСТРОЙКИ ---

    with _aqt_settings(urls, config.config_path) as aqt_config:
        # Воркеры run_installer — отдельные процессы (spawn), они перечитывают
        # настройки из Settings.configfile, поэтому конфиг нужен в виде файла
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False, encoding='utf-8') as temp_ini:
            aqt_config.write(temp_ini)
        old_configfile = Settings.configfile
        Settings.configfile = temp_ini.name

        try:
            # Создаём архивы
            qt_archives = QtArchives(
                os_name=config.host_os,
                target=config.platform_host_os,
                version_str=config.version,
                arch=config.arch,
                base=urls[0],
                modules=config.modules,
                is_include_base_package=True,  # включаем базовый пакет
                all_extra=False  # если нужны все модули, можно сделать True
            )

            packages = qt_archives.get_packages()

            install_path = config.install_path
            folder_created_by_us = False

            print(f"===TOTAL_PACKAGES:{len(packages)}===")
            print(f"Using baseurl: {Settings.baseurl}", file=sys.stderr)
            print(f"Using fallbacks: {Settings.fallbacks}", file=sys.stderr)
            if Settings.ignore_hash:
                print("WARNING: hash verification is DISABLED by "
                      "INSECURE_NOT_FOR_PRODUCTION_ignore_hash in the config", file=sys.stderr)
            else:
                print(f"Using hashes from: {Settings.trusted_mirrors}", file=sys.stderr)
            sys.stdout.flush()

            # Создаем папку
            if not install_path.exists():
                install_path.mkdir(parents=True, exist_ok=True)
                folder_created_by_us = True

            try:
                # Устанавливаем
                with tempfile.TemporaryDirectory() as temp_dir:
                    archive_dest = Path(temp_dir)
                    run_installer(packages, str(install_path), None, False, archive_dest, dry_run=False)

            except Exception as e:
                # Удаляем папку при ошибке установки, НО только если мы её сами создали
                if folder_created_by_us and install_path.exists():
                    shutil.rmtree(install_path, ignore_errors=True)
                raise e  # Пробрасываем ошибку дальше, чтобы main.py мог её перехватить

        finally:
            Settings.configfile = old_configfile
            os.unlink(temp_ini.name)
