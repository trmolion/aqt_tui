import configparser
import requests
import time
from pathlib import Path
from typing import Dict, List, Any



def is_successful(status_code: int) -> bool:
    return 200 <= status_code < 400



def get_urls_from_config(config_path: Path) -> List[str]:
    """Возвращает уникальные URL из конфига."""
    config = configparser.ConfigParser()
    config.read(config_path)
    urls = []
    
    baseurl = None
    if config.has_section('aqt'):
        baseurl = config.get('aqt', 'baseurl', fallback=None)
    if not baseurl and config.has_section('settings'):
        baseurl = config.get('settings', 'baseurl', fallback=None)
    if baseurl:
        urls.append(baseurl.strip())
    
    if config.has_section('mirrors'):
        fallbacks_str = config.get('mirrors', 'fallbacks', fallback='')
        if fallbacks_str:
            fallbacks = [u.strip() for u in fallbacks_str.split() if u.strip()]
            urls.extend(fallbacks)

    # удаляем дубликаты
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls



def check_single_server(url: str) -> Dict[str, Any]:
        """Проверяет один сервер и возвращает словарь с результатом."""
        # test_url = urljoin(url, "online/qtsdkrepository/")
        start = time.time()
        try:
            resp = requests.get(url, timeout=5, stream=True)
            elapsed = time.time() - start
            resp.close()
            return {
                'url': url,
                'status': is_successful(resp.status_code),
                'status_code': resp.status_code,
                'response_time': elapsed,
                'error': None
            }
        except requests.RequestException as e:
            elapsed = time.time() - start
            return {
                'url': url,
                'status': False,
                'status_code': None,
                'response_time': elapsed,
                'error': str(e)
            }


def check_servers_in_config(config_path: Path) -> List[Dict[str, Any]]:
    unique_urls = get_urls_from_config(config_path)

    results = []
    for url in unique_urls:
        # test_url = urljoin(url, "online/qtsdkrepository/")
        start = time.time()
        try:
            resp = requests.head(url, timeout=5, verify=True)
            elapsed = time.time() - start
            results.append({
                'url': url,
                'status': is_successful(resp.status_code),
                'status_code': resp.status_code,
                'response_time': elapsed,
                'error': None
            })
        except requests.RequestException as e:
            elapsed = time.time() - start
            results.append({
                'url': url,
                'status': False,
                'status_code': None,
                'response_time': elapsed,
                'error': str(e)
            })
            
    return results



def is_config_valid(config_path: Path) -> bool:
    """
    Проверяет, доступен ли хотя бы один сервер из конфига.
    """
    results = check_servers_in_config(config_path)
    # Если ни одного URL нет, возвращаем False (невалидный конфиг)
    if not results:
        return False
    # Иначе True, если хотя бы один сервер доступен
    return any(results.values())