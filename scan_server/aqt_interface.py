"""Утилиты для работы с aqtinstaller."""
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional

from aqt.archives import QtArchives
from aqt.installer import run_installer
from tempfile import TemporaryDirectory
from aqt.helper import Settings
from aqt.metadata import ArchiveId, MetadataFactory, Version, ModuleData

import shutil

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


def get_available_oses() -> List[str]:
    """Возвращает список поддерживаемых операционных систем."""
    return list(ArchiveId.TARGETS_FOR_HOST.keys())


def get_available_platform(host_os: str) -> List[str]:
    """Возвращает доступные архитектуры/компиляторы для заданной ОС."""
    return list(ArchiveId.TARGETS_FOR_HOST[host_os])
    

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


def get_available_architectures(urls: List[str], host_os: str, target: str, version: str) -> List[str]:
    """
    Возвращает список доступных архитектур для заданной версии Qt,
    используя переданные серверы.
    """
    if not urls:
        raise ValueError("No URLs provided")

    try:
        version_obj = Version(version)
    except ValueError as e:
        raise ValueError(f"Invalid version string: {version}") from e

    # Сохраняем текущие настройки
    old_baseurl = Settings._shared_state.get('_baseurl', None)
    old_fallbacks = Settings._shared_state.get('_fallbacks', None)
    old_trusted = Settings._shared_state.get('_trusted_mirrors', None)
    old_ignore = Settings._shared_state.get('_ignore_hash_override', None)

    try:
        # Временно подменяем настройки
        Settings._shared_state['_baseurl'] = urls[0]
        Settings._shared_state['_fallbacks'] = urls[1:] if len(urls) > 1 else [urls[0]]
        Settings._shared_state['_trusted_mirrors'] = urls  # все проверенные серверы считаем доверенными
        Settings._shared_state['_ignore_hash_override'] = True  # отключаем проверку хэша

        archive_id = ArchiveId("qt", host_os, target)
        meta = MetadataFactory(archive_id, base_url=urls[0])
        arches = meta.fetch_arches(version_obj)
        return arches if isinstance(arches, list) else []
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
        
        if old_trusted is not None:
            Settings._shared_state['_trusted_mirrors'] = old_trusted
        elif '_trusted_mirrors' in Settings._shared_state:
            del Settings._shared_state['_trusted_mirrors']

        if old_ignore is not None:
            Settings._shared_state['_ignore_hash_override'] = old_ignore
        elif '_ignore_hash_override' in Settings._shared_state:
            del Settings._shared_state['_ignore_hash_override']
            
            
def get_available_modules(urls: List[str], host_os: str, target: str, version: str, arch: str) -> ModuleData:
    """
    Возвращает список доступных модулей для заданной версии и архитектуры Qt,
    используя переданные серверы.
    """
    if not urls:
        raise ValueError("No URLs provided")

    try:
        version_obj = Version(version)
    except ValueError as e:
        raise ValueError(f"Invalid version string: {version}") from e

    # Сохраняем текущие настройки
    old_baseurl = Settings._shared_state.get('_baseurl', None)
    old_fallbacks = Settings._shared_state.get('_fallbacks', None)
    old_trusted = Settings._shared_state.get('_trusted_mirrors', None)
    old_ignore = Settings._shared_state.get('_ignore_hash_override', None)

    try:
        # Временно подменяем настройки
        Settings._shared_state['_baseurl'] = urls[0]
        Settings._shared_state['_fallbacks'] = urls[1:] if len(urls) > 1 else [urls[0]]
        Settings._shared_state['_trusted_mirrors'] = urls  # все проверенные серверы считаем доверенными
        Settings._shared_state['_ignore_hash_override'] = True  # отключаем проверку хэша

        modules_id = ArchiveId("qt", host_os, target)
        meta = MetadataFactory(modules_id, base_url=urls[0])
        modules = meta.fetch_long_modules(version_obj, arch)
        return modules
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
        
        if old_trusted is not None:
            Settings._shared_state['_trusted_mirrors'] = old_trusted
        elif '_trusted_mirrors' in Settings._shared_state:
            del Settings._shared_state['_trusted_mirrors']

        if old_ignore is not None:
            Settings._shared_state['_ignore_hash_override'] = old_ignore
        elif '_ignore_hash_override' in Settings._shared_state:
            del Settings._shared_state['_ignore_hash_override']
            
            
    
    
def run_installation_with_urls(config: AqtConfig, urls: List[str]) -> None:
    """
    Устанавливает Qt, используя переданные серверы.
    """
    if not urls:
        raise ValueError("No URLs provided")
    
    # Временно подменяем настройки, как ранее
    old_baseurl = Settings._shared_state.get('_baseurl', None)
    old_fallbacks = Settings._shared_state.get('_fallbacks', None)
    old_trusted = Settings._shared_state.get('_trusted_mirrors', None)
    old_ignore = Settings._shared_state.get('_ignore_hash_override', None)
    
    try:
        Settings._shared_state['_baseurl'] = urls[0]
        Settings._shared_state['_fallbacks'] = urls[1:] if len(urls) > 1 else [urls[0]]
        Settings._shared_state['_trusted_mirrors'] = urls
        Settings._shared_state['_ignore_hash_override'] = True  # отключаем проверку хэша для скорости
        
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
        
        # import logging
        # logging.getLogger("aqt").info(f"===TOTAL_PACKAGES:{len(packages)}===")
        
        import sys
        print(f"===TOTAL_PACKAGES:{len(packages)}===")
        sys.stdout.flush()

        # 1. Создаем папку, если её физически не существует
        if not install_path.exists():
            install_path.mkdir(parents=True, exist_ok=True)
            folder_created_by_us = True
        
        try:
            # Устанавливаем
            with TemporaryDirectory() as temp_dir:
                archive_dest = Path(temp_dir)
                run_installer(packages, str(install_path), None, False, archive_dest, dry_run=False)
                
        except Exception as e:
            # 2. Удаляем папку при ошибке установки, НО только если мы её сами создали
            if folder_created_by_us and install_path.exists():
                shutil.rmtree(install_path, ignore_errors=True)
            raise e  # Пробрасываем ошибку дальше, чтобы main.py мог её перехватить
            
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
        
        if old_trusted is not None:
            Settings._shared_state['_trusted_mirrors'] = old_trusted
        elif '_trusted_mirrors' in Settings._shared_state:
            del Settings._shared_state['_trusted_mirrors']

        if old_ignore is not None:
            Settings._shared_state['_ignore_hash_override'] = old_ignore
        elif '_ignore_hash_override' in Settings._shared_state:
            del Settings._shared_state['_ignore_hash_override']