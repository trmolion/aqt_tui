"""Поиск уже установленных Qt (раскладка aqt / официального установщика: <root>/<версия>/<arch_dir>)."""
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple

# rc-файлы оболочек, из которых берутся пути (export PATH=..., CMAKE_PREFIX_PATH=..., Qt6_DIR=...)
RC_FILES = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile", ".zshenv")

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_QMAKE_NAMES = ("qmake", "qmake6", "qmake.exe", "qtpaths", "qtpaths6", "qtpaths.exe")
_MAX_PARENTS = 5  # путь может указывать вглубь Qt: .../gcc_64/lib/cmake/Qt6

# Обход домашней папки: ~/Downloads/папка/подпапка/6.8.3/gcc_64 — глубина 5
_HOME_DEPTH = 5
_HOME_TIME_LIMIT = 2.0  # секунды — на случай огромной домашней папки
_HOME_SKIP = {"node_modules", "__pycache__", "site-packages", "venv", "build", "target"}


@dataclass
class InstalledQt:
    prefix: Path        # .../Qt/6.8.3/gcc_64
    version: str        # 6.8.3
    source: str         # где найден: PATH, ~/.zshrc, ~/Qt
    # заполняются после запроса к серверу (resolve_installed_arch)
    target: Optional[str] = field(default=None, compare=False)
    arch: Optional[str] = field(default=None, compare=False)
    host_os: Optional[str] = field(default=None, compare=False)

    @property
    def arch_dir(self) -> str:
        return self.prefix.name

    @property
    def root(self) -> Path:
        """Папка, в которую ставил aqt (её передаём как install_path)."""
        return self.prefix.parent.parent

    @property
    def title(self) -> str:
        return f"Qt {self.version} ({self.arch_dir})"

    @property
    def location(self) -> str:
        """Папка установки, домашняя папка сокращена до ~."""
        home = str(Path.home())
        root = str(self.root)
        return "~" + root[len(home):] if root.startswith(home) else root


def _qt_version(prefix: Path) -> Optional[str]:
    qconfig = prefix / "mkspecs" / "qconfig.pri"
    try:
        for line in qconfig.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "QT_VERSION":
                return value.strip()
    except OSError:
        pass
    return prefix.parent.name if _VERSION_RE.match(prefix.parent.name) else None


def _find_prefix(path: Path) -> Optional[Path]:
    """Поднимается от path к папке Qt вида <root>/<версия>/<arch_dir> с bin/qmake."""
    for candidate in [path, *path.parents][:_MAX_PARENTS + 1]:
        bin_dir = candidate / "bin"
        if any((bin_dir / name).exists() for name in _QMAKE_NAMES):
            # системный Qt (/usr/bin/qmake) aqt не дополнит — нужна раскладка <версия>/<arch_dir>
            if _VERSION_RE.match(candidate.parent.name):
                return candidate
            return None
    return None


def _paths_from_rc(text: str) -> Iterator[str]:
    """Пути из строк rc-файла: значения переменных, списки через «:», пути в кавычках с пробелами."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            tokens = line.split()
        for token in tokens:
            value = token.partition("=")[2] if "=" in token else token
            for piece in value.split(":"):
                piece = os.path.expanduser(os.path.expandvars(piece.strip()))
                if piece.startswith("/"):
                    yield piece


def _candidates() -> Iterator[Tuple[Path, str]]:
    home = Path.home()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            yield Path(entry), "PATH"
    for name in RC_FILES:
        rc = home / name
        try:
            text = rc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for path in _paths_from_rc(text):
            yield Path(path), f"~/{name}"
    yield from _home_candidates(home)


def _home_candidates(home: Path) -> Iterator[Tuple[Path, str]]:
    """Ограниченный по глубине и времени обход домашней папки (без скрытых каталогов)."""
    deadline = time.monotonic() + _HOME_TIME_LIMIT
    for root, subdirs, _ in os.walk(home):
        if time.monotonic() > deadline:
            return
        path = Path(root)
        if any((path / "bin" / name).exists() for name in _QMAKE_NAMES):
            subdirs[:] = []  # внутрь Qt не спускаемся
            yield path, "поиск в ~"
            continue
        if len(path.relative_to(home).parts) >= _HOME_DEPTH:
            subdirs[:] = []
            continue
        subdirs[:] = sorted(d for d in subdirs if not d.startswith(".") and d not in _HOME_SKIP)


def find_installed_qts() -> List[InstalledQt]:
    """Все найденные Qt без повторов, в порядке обнаружения."""
    found: List[InstalledQt] = []
    seen: Set[Path] = set()
    for path, source in _candidates():
        try:
            prefix = _find_prefix(path)
            if prefix is None:
                continue
            resolved = prefix.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        version = _qt_version(prefix)
        if version:
            seen.add(resolved)
            found.append(InstalledQt(prefix=resolved, version=version, source=source))
    return sorted(found, key=lambda q: (str(q.root), [int(x) for x in q.version.split(".")], q.arch_dir))


def find_system_qt() -> Optional[Tuple[str, str]]:
    """
    Qt из пакетного менеджера (qmake в /usr и т.п.) — (версия, prefix). Модули к нему aqt не ставит:
    это сломало бы пакеты системы, поэтому он только показывается пользователю.
    """
    for name in ("qmake6", "qmake"):
        qmake = shutil.which(name)
        if not qmake:
            continue
        try:
            out = subprocess.run([qmake, "-query"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        values = dict(line.split(":", 1) for line in out.splitlines() if ":" in line)
        version, prefix = values.get("QT_VERSION"), values.get("QT_INSTALL_PREFIX")
        if version and prefix and _find_prefix(Path(prefix)) is None:
            return version, prefix
    return None


def installed_modules(prefix: Path) -> Set[str]:
    """
    Имена установленных модулей в терминах aqt (qtcharts, qtmultimedia, …).
    Источники: sbom/<модуль>-<версия>.spdx (Qt >= 6.8) и поле "repository" в modules/*.json (Qt 6).
    Для Qt 5 таких файлов нет — вернётся пустое множество.
    """
    modules: Set[str] = set()
    for spdx in (prefix / "sbom").glob("*.spdx"):
        name = re.match(r"^(.+?)-\d+\.\d+\.\d+", spdx.name)
        if name:
            modules.add(name.group(1))
    for module_json in (prefix / "modules").glob("*.json"):
        try:
            repository = json.loads(module_json.read_text(encoding="utf-8")).get("repository")
        except (OSError, ValueError):
            continue
        if repository:
            modules.add(repository)
    return modules
