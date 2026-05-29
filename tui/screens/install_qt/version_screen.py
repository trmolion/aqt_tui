from typing import Callable, Dict, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, ProgressBar, Tree

from scan_server.aqt_interface import get_versions_tree_with_config


class VersionWidget(Widget):
    """Виджет выбора версии Qt. Монтируется в right_panel."""

    DEFAULT_CSS = "VersionWidget { height: 100%; }"

    def __init__(
        self,
        working_urls: List[str],
        host_os: str,
        platform: str,
        on_done: Callable[[Optional[str]], None],
        cached_tree: Optional[Dict] = None,
    ) -> None:
        super().__init__()
        self._working_urls = working_urls
        self._host_os = host_os
        self._platform = platform
        self._on_done = on_done
        self._cached_tree = cached_tree

    def compose(self) -> ComposeResult:
        yield Vertical(id="version_content")

    def on_mount(self) -> None:
        if self._cached_tree:
            self._render_tree(self._cached_tree)
        else:
            self._show_loading()
            self._fetch_worker(self._working_urls)

    # -------------------------------------------------------------------------
    # Состояния
    # -------------------------------------------------------------------------

    def _show_loading(self) -> None:
        content = self.query_one("#version_content")
        content.remove_children()
        container = Vertical(id="loading_container")
        content.mount(container)
        container.mount(Label("Загрузка версий Qt..."))
        container.mount(ProgressBar(total=None, show_eta=False))

    def _render_tree(self, tree_dict: Dict) -> None:
        content = self.query_one("#version_content")
        content.remove_children()
        tree = Tree("Доступные версии Qt", id="version_tree")
        tree.root.expand()
        for major, versions in sorted(tree_dict.items(), reverse=True):
            node = tree.root.add(str(major), expand=True)
            for version in versions:
                node.add_leaf(version)
        content.mount(tree)
        tree.focus()

    # -------------------------------------------------------------------------
    # Загрузка данных
    # -------------------------------------------------------------------------

    @work(thread=True)
    def _fetch_worker(self, working_urls: List[str]) -> None:
        try:
            tree_dict = get_versions_tree_with_config(working_urls, self._host_os, self._platform)
            if not tree_dict:
                self.app.call_from_thread(
                    self.notify, "Нет доступных версий для выбранной конфигурации", severity="warning"
                )
                self.app.call_from_thread(self._on_done, None)
                return
            self.app._versions_cache[(self._host_os, self._platform)] = tree_dict
            self.app.call_from_thread(self._render_tree, tree_dict)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Ошибка получения версий: {e}", severity="error")
            self.app.call_from_thread(self._on_done, None)

    # -------------------------------------------------------------------------
    # События
    # -------------------------------------------------------------------------

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        if event.node.is_root:
            return
        if event.node.children:
            event.node.toggle()
        else:
            self._on_done(event.node.label.plain)
