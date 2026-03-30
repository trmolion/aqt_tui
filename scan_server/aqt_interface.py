"""Утилиты для работы с aqtinstaller."""
from pathlib import Path
from typing import Dict, List, Optional

import aqt.installer
from aqt.metadata import ArchiveId
# from aqt.settings import Settings

class AqtConfig:
    """Хранит и управляет настройками установки Qt."""
    def __init__(self):
        self.config_path: Optional[Path] = None
        self.host_os: Optional[str] = None      # 'windows', 'linux', 'mac'
        self.target: str = 'desktop'            # 'desktop' или 'android'
        self.version: Optional[str] = None
        self.arch: Optional[str] = None          # компилятор, архитектура
        self.modules: List[str] = []             # например, ['debug_info', 'qtdatavis3d']
        self.install_path: Optional[Path] = None

    def is_valid(self) -> bool:
        """Проверяет, заполнены ли все обязательные поля."""
        return all([
            self.config_path,
            self.host_os,
            self.target,
            self.version,
            self.arch,
            self.install_path
        ])

def load_config_from_ini(path: Path) -> Dict:
    """Загружает настройки из aqt.ini (если нужно)."""
    # Здесь можно реализовать парсинг INI, если требуется.
    # Пока просто заглушка.
    return {}

def get_available_oses() -> List[str]:
    """Возвращает список поддерживаемых операционных систем."""
    return list(ArchiveId.TARGETS_FOR_HOST.keys())

def get_available_platform(host_os: str) -> List[str]:
    """Возвращает доступные архитектуры/компиляторы для заданной ОС."""
    # Это примерные данные, реальные нужно брать из aqt или из API
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