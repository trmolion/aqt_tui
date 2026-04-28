#!/usr/bin/env python3
import os
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scan_server.aqt_interface import AqtConfig, run_installation_with_urls

def setup_logging(log_file_path: Path):
    """Настройка логирования: вывод в stdout и в файл."""
    # Снимаем все старые обработчики корневого логгера
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter('%(message)s')

    # Обработчик для stdout (отображается в TUI)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Создаём папку для лога, если нужно
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    # Обработчик для файла install.log
    file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Уровень корневого логгера – DEBUG, чтобы ваще всё писалось
    root_logger.setLevel(logging.DEBUG)

    # Логгер aqt должен передавать сообщения родительскому (root), это по умолчанию True
    aqt_logger = logging.getLogger("aqt")
    aqt_logger.setLevel(logging.DEBUG)
    aqt_logger.propagate = True


def main():
    if len(sys.argv) != 2:
        print("Usage: install_worker.py <config_json_file>")
        sys.exit(1)
    
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

    if config.install_path:
        log_file = config.install_path / "install_qt.log"
        setup_logging(log_file)
        print(f"=== INSTALLATION LOG WILL BE SAVED TO {log_file} ===", flush=True)
    else:
        # Если путь не задан то пишем только в stdout
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format='%(message)s')
    
    original_cwd = os.getcwd()
    try:
        print("=== INSTALLATION STARTED ===", flush=True)
        # Пошла установка
        os.chdir(config.install_path)
        run_installation_with_urls(config, working_urls)
        
        # Ну и для красоты
        print("=== INSTALLATION SUCCESS ===", flush=True)

    except SystemExit as e:
        # sys.exit(0) - это нормальное завершение
        if e.code == 0 or e.code is None:
            print("=== INSTALLATION SUCCESS ===", flush=True)
        else:
            print(f"=== INSTALLATION FAILED WITH CODE {e.code} ===", flush=True)
            sys.exit(e.code)
            
    except Exception as e:
        # Ловим все остальные ошибки
        print(f"=== INSTALLATION FAILED: {str(e)} ===", flush=True)
        sys.exit(1)
        
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    main()