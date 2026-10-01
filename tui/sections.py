"""Разделы главного меню: какие шаги нужно пройти и что в итоге устанавливается."""
from typing import Any, Dict, List, Optional, Tuple

from scan_server.aqt_interface import TOOLS, AqtConfig

QT_STEPS = ["host_os", "platform", "version", "arch", "modules", "path"]

# ключ раздела → (название, шаги, что будет установлено)
SECTIONS: Dict[str, Tuple[str, List[str], str]] = {
    "all": ("Всё", QT_STEPS, "Qt с модулями, Qt Creator, CMake, Ninja и документация"),
    "qt": ("Qt", QT_STEPS, "Qt с выбранными модулями"),
    "creator": ("Qt Creator", ["host_os", "path"], "Qt Creator (последняя версия)"),
    "docs": ("Документация", ["host_os", "version", "doc_modules", "path"], "документация Qt"),
    "examples": ("Примеры", ["host_os", "version", "example_modules", "path"], "примеры Qt"),
    "tools": ("Инструменты", ["host_os", "tools", "path"], "выбранные инструменты"),
}

# Инструменты, которые входят в «Всё»
ALL_TOOLS = ["tools_qtcreator_gui", "tools_cmake", "tools_ninja"]

# шаг → (название кнопки, подпись в сводке)
STEPS: Dict[str, Tuple[str, str]] = {
    "host_os": ("Выбор ОС", "ОС"),
    "platform": ("Выбор платформы", "Платформа"),
    "version": ("Выбор версии Qt", "Версия Qt"),
    "arch": ("Выбор компилятора", "Компилятор/архитектура"),
    "modules": ("Выбор модулей", "Модули"),
    "doc_modules": ("Модули документации", "Модули документации"),
    "example_modules": ("Модули примеров", "Модули примеров"),
    "tools": ("Выбор инструментов", "Инструменты"),
    "path": ("Путь установки", "Путь установки"),
}

# шаг → поле AqtConfig
STEP_FIELDS: Dict[str, str] = {
    "host_os": "host_os",
    "platform": "platform_host_os",
    "version": "version",
    "arch": "arch",
    "modules": "modules",
    "doc_modules": "doc_modules",
    "example_modules": "example_modules",
    "tools": "tools",
    "path": "install_path",
}


def step_value(step: str, config: AqtConfig) -> Any:
    return getattr(config, STEP_FIELDS[step])


def step_done(step: str, config: AqtConfig) -> bool:
    value = step_value(step, config)
    if step == "tools":
        return bool(value)
    # у списков модулей пустой список — тоже ответ («без дополнительных модулей»)
    return value is not None and value != ""


def format_step_value(step: str, config: AqtConfig) -> str:
    value = step_value(step, config)
    if value is None:
        return "не выбрано"
    if step == "tools":
        return ", ".join(TOOLS.get(tool, tool) for tool, _ in value) or "не выбрано"
    if isinstance(value, list):
        return ", ".join(value) or "без дополнительных"
    return str(value)


def version_target(section: str, config: AqtConfig) -> Optional[str]:
    """Платформа, для которой показывать версии: у документации и примеров — всегда desktop."""
    return "desktop" if section in ("docs", "examples") else config.platform_host_os


def build_plan(section: str, config: AqtConfig) -> Dict[str, Any]:
    """План для install_worker: что именно ставить в выбранном разделе."""
    plan: Dict[str, Any] = {"qt": section in ("all", "qt"), "tools": [], "docs": None, "examples": None}
    if section == "all":
        plan["tools"] = [[tool, None] for tool in ALL_TOOLS]
        plan["docs"] = list(config.modules or [])  # лишние модули отфильтрует установщик
    elif section == "creator":
        plan["tools"] = [["tools_qtcreator_gui", None]]
    elif section == "tools":
        plan["tools"] = [list(tool) for tool in config.tools or []]
    elif section == "docs":
        plan["docs"] = list(config.doc_modules or [])
    elif section == "examples":
        plan["examples"] = list(config.example_modules or [])
    return plan
