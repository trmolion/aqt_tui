"""Загрузка .ini-конфига aqt по ссылке (обычный URL или страница GitHub Gist)."""
import configparser
import hashlib
import os
import re
from pathlib import Path
from typing import List, Optional

import requests

from scan_server.check_servers import get_urls_from_config

DEFAULT_CONFIG_URL = "https://gist.github.com/pandazz77/a8a00ccf5e1d8b4d8289337f4cedbfd4"

# https://gist.github.com/<user>/<id>#file-aqt-ini (user и якорь необязательны)
_GIST_PAGE_RE = re.compile(
    r"^https?://gist\.github\.com/(?:(?P<user>[\w-]+)/)?(?P<id>[0-9a-f]+)/?(?:#(?P<anchor>[\w-]+))?$", re.I
)
_TIMEOUT = 10


def cache_dir() -> Path:
    """Папка, куда сохраняются скачанные конфиги."""
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "aqt-tui" / "configs"


def _gist_anchor(filename: str) -> str:
    """Якорь, который GitHub ставит файлу на странице gist: aqt.ini → file-aqt-ini."""
    return "file-" + re.sub(r"[^a-z0-9]+", "-", filename.lower()).strip("-")


def _raw_urls_from_api(gist_id: str, anchor: Optional[str]) -> List[str]:
    """Ссылка на файл через GitHub API — нужна, только если в ссылке нет имени пользователя."""
    resp = requests.get(f"https://api.github.com/gists/{gist_id}", timeout=_TIMEOUT)
    resp.raise_for_status()
    files = list(resp.json()["files"].values())
    chosen: Optional[dict] = None
    if anchor:
        chosen = next((f for f in files if _gist_anchor(f["filename"]) == anchor.lower()), None)
    if chosen is None:
        chosen = next((f for f in files if f["filename"].endswith(".ini")), None)
    if chosen is None:
        raise ValueError("В gist нет .ini-файла")
    return [chosen["raw_url"]]


def candidate_raw_urls(url: str) -> List[str]:
    """
    Ссылки, по которым можно скачать сам .ini, — по порядку попыток.
    Обычная ссылка возвращается как есть. Для страницы gist с именем пользователя
    сырой файл доступен напрямую (без GitHub API и его лимита 60 запросов в час):
    сначала файл из якоря (#file-aqt-ini → aqt.ini), потом первый файл gist.
    """
    url = url.strip()
    m = _GIST_PAGE_RE.match(url)
    if not m:
        return [url]
    if not m["user"]:
        return _raw_urls_from_api(m["id"], m["anchor"])

    base = f"https://gist.githubusercontent.com/{m['user']}/{m['id']}/raw"
    candidates = []
    anchor = (m["anchor"] or "").lower()
    if anchor.startswith("file-"):
        stem, _, ext = anchor.removeprefix("file-").rpartition("-")
        if stem:
            candidates.append(f"{base}/{stem}.{ext}")
    return candidates + [base]


def download_config(url: str) -> Path:
    """
    Скачивает конфиг по ссылке, проверяет, что это корректный .ini с серверами,
    и сохраняет его в кеш. В кеше остаётся только он — предыдущие копии удаляются.
    Возвращает путь к локальной копии.
    """
    error: Optional[Exception] = None
    for raw_url in candidate_raw_urls(url):
        try:
            resp = requests.get(raw_url, timeout=_TIMEOUT)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            error = e
    else:
        raise error
    text = resp.text

    configparser.ConfigParser().read_string(text)  # бросает configparser.Error на битом .ini

    path = cache_dir() / f"{hashlib.sha1(url.strip().encode()).hexdigest()[:12]}.ini"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if not get_urls_from_config(path):
        path.unlink()
        raise ValueError("В конфиге нет ни baseurl, ни fallbacks")

    # Имя файла зависит от ссылки, поэтому при смене ссылки меняется и путь — по нему App
    # понимает, что конфиг другой, и сбрасывает кеш метаданных
    for old in path.parent.glob("*.ini"):
        if old != path:
            old.unlink(missing_ok=True)
    return path
