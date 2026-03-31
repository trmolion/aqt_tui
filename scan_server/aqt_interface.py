"""Утилиты для работы с aqtinstaller."""
from pathlib import Path
from typing import Dict, List, Optional

import aqt.installer
from aqt.helper import Settings
from aqt.metadata import ArchiveId, MetadataFactory, Version

class AqtConfig:
    """Хранит и управляет настройками установки Qt."""
    def __init__(self):
        self.config_path: Optional[Path] = None
        self.host_os: Optional[str] = None      # 'windows', 'linux', 'mac'
        self.platform_host_os: Optional[str] = None
        self.version: Optional[str] = None
        self.arch: Optional[str] = None          # компилятор, архитектура
        self.modules: List[str] = []             # например, ['debug_info', 'qtdatavis3d']
        self.install_path: Optional[Path] = None

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
    

def get_versions_tree_with_config(urls: List[str], host_os: str, target: str) -> Dict[int, List[str]]:
    """
    Возвращает дерево версий Qt, используя переданные серверы.
    Первый URL в списке используется как baseurl, остальные как fallbacks.
    """
    if not urls:
        raise ValueError("No URLs provided")

    # Сохраняем текущие значения из _shared_state
    old_baseurl = Settings._shared_state.get('_baseurl', None)
    old_fallbacks = Settings._shared_state.get('_fallbacks', None)

    try:
        # Временно подменяем настройки
        Settings._shared_state['_baseurl'] = urls[0]
        Settings._shared_state['_fallbacks'] = urls[1:] if len(urls) > 1 else []

        archive_id = ArchiveId("qt", host_os, target)
        meta = MetadataFactory(archive_id, base_url=urls[0])
        versions = meta.fetch_versions().flattened()
    finally:
        # Восстанавливаем настройки
        if old_baseurl is not None:
            Settings._shared_state['_baseurl'] = old_baseurl
        elif '_baseurl' in Settings._shared_state:
            del Settings._shared_state['_baseurl']

        if old_fallbacks is not None:
            Settings._shared_state['_fallbacks'] = old_fallbacks
        elif '_fallbacks' in Settings._shared_state:
            del Settings._shared_state['_fallbacks']

    tree = {}
    for ver in versions:
        tree.setdefault(ver.major, []).append(str(ver))
    for major in tree:
        tree[major].sort(key=lambda v: Version(v))
    return tree


def load_config_from_ini(path: Path) -> Dict:
    """Загружает настройки из aqt.ini."""
    # Здесь можно реализовать парсинг INI, если требуется.
    # Пока просто заглушка.
    return {}

def get_available_oses() -> List[str]:
    """Возвращает список поддерживаемых операционных систем."""
    return list(ArchiveId.TARGETS_FOR_HOST.keys())

def get_available_platform(host_os: str) -> List[str]:
    """Возвращает доступные архитектуры/компиляторы для заданной ОС."""
    return list(ArchiveId.TARGETS_FOR_HOST[host_os])

def get_available_modules(host_os: str, version: str, arch: str) -> List[str]:
    """Возвращает список доступных модулей для данной конфигурации."""
    # В реальности нужно вызывать aqt list-qt или подобное
    return ['debug_info', 'qtdatavis3d', 'qtcharts', 'qtwebengine']

def run_installation(config: AqtConfig) -> None:
    aqt.installer.install(
        host=config.host_os,
        target=config.target,
        version=config.version,
        arch=config.arch,
        modules=config.modules,
        outputdir=str(config.install_path)
    )