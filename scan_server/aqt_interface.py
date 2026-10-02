"""Утилиты для работы с aqtinstaller."""
import logging
import os
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import aqt
from aqt.archives import QtArchives, QtPackage, SrcDocExamplesArchives, ToolArchives
from aqt.exceptions import ArchiveDownloadError
from aqt.helper import MyConfigParser, Settings, retry_on_bad_connection
from aqt.installer import Cli, run_installer
from aqt.metadata import ArchiveId, MetadataFactory, ModuleData, QtRepoProperty, Version
from aqt.updater import Updater


# settings.ini, который aqt читает по умолчанию
_AQT_DEFAULT_INI = Path(aqt.__file__).parent / "settings.ini"

# Settings в aqt — глобальный объект (Borg). Воркеры TUI работают в разных потоках,
# поэтому подменять его конфиг можно только по очереди.
_settings_lock = threading.Lock()

# Инструменты, которые можно выбрать в разделе «Инструменты»: имя в репозитории → название
TOOLS: Dict[str, str] = {
    "tools_qtcreator_gui": "Qt Creator",
    "tools_cmake": "CMake",
    "tools_ninja": "Ninja",
    "tools_conan": "Conan",
    "tools_ifw": "Qt Installer Framework",
}

# Смена поля сбрасывает поля, которые от него зависят
_DEPENDENTS: Dict[str, Tuple[str, ...]] = {
    "host_os": ("platform_host_os", "version", "arch", "modules", "doc_modules", "example_modules", "tools"),
    "platform_host_os": ("version", "arch", "modules", "doc_modules", "example_modules"),
    "version": ("arch", "modules", "doc_modules", "example_modules"),
    "arch": ("modules",),
}


class AqtConfig:
    """Хранит и управляет настройками установки Qt."""
    def __init__(self):
        self.config_path: Optional[Path] = None     # путь с конфигом для установки
        self.host_os: Optional[str] = None          # 'windows', 'linux', 'mac'
        self.platform_host_os: Optional[str] = None # под какой компилятор Qt
        self.version: Optional[str] = None          # версия qt
        self.arch: Optional[str] = None             # компилятор, архитектура
        self.install_path: Optional[Path] = None    # путь установки qt
        # Списки: None — шаг ещё не пройден, [] — пройден, ничего не выбрано
        self.modules: Optional[List[str]] = None          # модули Qt
        self.doc_modules: Optional[List[str]] = None      # модули документации
        self.example_modules: Optional[List[str]] = None  # модули примеров
        self.tools: Optional[List[Tuple[str, str]]] = None  # (имя инструмента, вариант)

    def set(self, field: str, value: Any) -> None:
        """Меняет поле; если значение другое — сбрасывает зависящие от него поля."""
        if getattr(self, field) == value:
            return
        setattr(self, field, value)
        for dependent in _DEPENDENTS.get(field, ()):
            setattr(self, dependent, None)


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


def resolve_installed_arch(
    urls: List[str], host_os: str, version: str, arch_dir: str, config_path: Optional[Path] = None,
) -> Tuple[str, str, str]:
    """
    По папке установленного Qt (gcc_64, android_arm64_v8a, …) находит (host_os, target, arch) в терминах aqt.
    Перебирает платформы хоста и all_os (wasm), сравнивая имя папки с каталогом каждой архитектуры.
    """
    version_obj = Version(version)
    with _aqt_settings(urls, config_path):
        for host in (host_os, "all_os"):
            for target in ArchiveId.TARGETS_FOR_HOST[host]:
                if target == "qt":
                    continue  # all_os/qt — только документация и примеры
                try:
                    meta = MetadataFactory(ArchiveId("qt", host, target), base_url=urls[0])
                    arches = meta.fetch_arches(version_obj)
                except ArchiveDownloadError:
                    continue  # этой версии нет для платформы
                for arch in arches:
                    if QtRepoProperty.get_arch_dir_name(host, arch, version_obj) == arch_dir:
                        return host, target, arch
    raise ValueError(f"Не удалось определить архитектуру Qt {version} для папки {arch_dir}")


def _sde_location(host_os: str, version: str) -> Tuple[str, str]:
    """Где лежат документация и примеры: для Qt >= 6.7 — в общем разделе all_os/qt (как в aqt)."""
    if Version(version) >= Version("6.7.0"):
        return "all_os", "qt"
    return host_os, "desktop"


def get_sde_modules(
    urls: List[str], host_os: str, version: str, flavor: str, config_path: Optional[Path] = None,
) -> List[str]:
    """Возвращает модули документации (flavor="doc") или примеров (flavor="examples") для версии Qt."""
    os_name, target = _sde_location(host_os, version)
    with _aqt_settings(urls, config_path):
        meta = MetadataFactory(ArchiveId("qt", os_name, target), base_url=urls[0])
        return sorted(meta.fetch_modules_sde(flavor, Version(version)))


def _main_tool_variant(tool_name: str, listing: Dict[str, Dict[str, str]]) -> Optional[str]:
    """
    Основной вариант инструмента. Без явного варианта aqt ставит все сразу —
    для Qt Creator это ещё исходники, телеметрия и отладочные символы.
    """
    preferred = "qt.tools." + tool_name.removeprefix("tools_")
    if preferred in listing:
        return preferred
    return next(iter(listing), None)


def get_tools_info(urls: List[str], host_os: str, config_path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Возвращает доступные для host_os инструменты из TOOLS: tool, variant, title."""
    result = []
    with _aqt_settings(urls, config_path):
        meta = MetadataFactory(ArchiveId("tools", host_os, "desktop"), base_url=urls[0])
        for tool_name, title in TOOLS.items():
            try:
                listing = meta.fetch_tool_long_listing(tool_name).table_data
            except ArchiveDownloadError:
                continue  # инструмента нет для этой ОС
            variant = _main_tool_variant(tool_name, listing)
            if variant:
                result.append({
                    "tool": tool_name,
                    "variant": variant,
                    "title": listing[variant].get("DisplayName") or title,
                })
    return result


# =============================================================================
# Установка
# =============================================================================

def _collect_packages(config: AqtConfig, base: str, plan: Dict[str, Any]) -> Tuple[List[QtPackage], Any]:
    """Собирает пакеты всех компонентов плана. Возвращает (пакеты, target_config Qt или None)."""
    packages: List[QtPackage] = []
    qt_target = None

    if plan.get("qt"):
        qt_archives = retry_on_bad_connection(
            lambda base_url: QtArchives(
                os_name=config.host_os,
                target=config.platform_host_os,
                version_str=config.version,
                arch=config.arch,
                base=base_url,
                modules=config.modules or None,
                # False — доустановка модулей к уже установленному Qt (как `aqt install-qt --noarchives`)
                is_include_base_package=plan.get("qt_base", True),
                all_extra=False  # если нужны все модули, можно сделать True
            ),
            base,
        )
        packages += qt_archives.get_packages()
        # Патчить qmake и qt.conf нужно только при установке базового пакета (как в aqt)
        if plan.get("qt_base", True):
            qt_target = qt_archives.get_target_config()
            qt_target.os_name = Cli._get_effective_os_name(config.host_os)

    for tool_name, variant in plan.get("tools", []):
        if variant is None:
            meta = MetadataFactory(ArchiveId("tools", config.host_os, "desktop"), base_url=base)
            variant = _main_tool_variant(tool_name, meta.fetch_tool_long_listing(tool_name).table_data)
        tool_archives = retry_on_bad_connection(
            lambda base_url: ToolArchives(
                os_name=config.host_os, target="desktop", tool_name=tool_name, base=base_url, arch=variant,
            ),
            base,
        )
        packages += tool_archives.get_packages()

    for flavor, key in (("doc", "docs"), ("examples", "examples")):
        modules = plan.get(key)
        if modules is None:
            continue
        os_name, target = _sde_location(config.host_os, config.version)
        # В «Всё» передаются модули Qt — оставляем только те, для которых есть документация
        meta = MetadataFactory(ArchiveId("qt", os_name, target), base_url=base)
        available = set(meta.fetch_modules_sde(flavor, Version(config.version)))
        modules = [m for m in modules if m in available]
        sde_archives = retry_on_bad_connection(
            lambda base_url: SrcDocExamplesArchives(
                flavor, os_name, target, config.version, base_url, modules=modules or None,
            ),
            base,
        )
        packages += sde_archives.get_packages()

    return packages, qt_target


def run_installation_with_urls(config: AqtConfig, urls: List[str], plan: Dict[str, Any]) -> None:
    """
    Устанавливает компоненты по плану, используя переданные серверы:
        plan = {"qt": bool, "qt_base": bool (по умолчанию True; False — только модули),
                "tools": [[имя инструмента, вариант или None], ...],
                "docs": [модули] или None, "examples": [модули] или None}
    Всё ставится одним вызовом run_installer в config.install_path.
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
            packages, qt_target = _collect_packages(config, urls[0], plan)

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

                # Как в `aqt install-qt`: qt.conf, qconfig.pri, пути в qmake и т.п.
                if qt_target is not None:
                    desktop_dir, _ = Cli()._get_autodesktop_dir_and_arch(
                        False, config.host_os, config.platform_host_os, install_path,
                        Version(config.version), config.arch,
                    )
                    Updater.update(qt_target, install_path, desktop_dir)

            except Exception as e:
                # Удаляем папку при ошибке установки, НО только если мы её сами создали
                if folder_created_by_us and install_path.exists():
                    shutil.rmtree(install_path, ignore_errors=True)
                raise e  # Пробрасываем ошибку дальше, чтобы main.py мог её перехватить

        finally:
            Settings.configfile = old_configfile
            os.unlink(temp_ini.name)
