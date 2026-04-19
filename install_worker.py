#!/usr/bin/env python3
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scan_server.aqt_interface import AqtConfig, run_installation_with_urls

def main():
    if len(sys.argv) != 2:
        print("Usage: install_worker.py <config_json_file>")
        sys.exit(1)
        
    # Отключаем файловый логгер aqt
    for handler in logging.root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logging.root.removeHandler(handler)
    # Настраиваем вывод в stdout
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='%(message)s')

    json_path = Path(sys.argv[1])
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    config = AqtConfig()
    config.config_path = Path(data['config_path']) if data['config_path'] else None
    config.host_os = data['host_os']
    config.platform_host_os = data['platform_host_os']
    config.version = data['version']
    config.arch = data['arch']
    config.modules = data['modules']
    config.install_path = Path(data['install_path']) if data['install_path'] else None

    working_urls = data['working_urls']

    # Настраиваем логгер aqt для вывода в stdout
    aqt_logger = logging.getLogger("aqt")
    aqt_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    aqt_logger.addHandler(handler)
    
    try:
        print("=== INSTALLATION STARTED ===", flush=True)
        run_installation_with_urls(config, working_urls)
        print("SUCCESS", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()