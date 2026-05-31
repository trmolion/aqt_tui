import os
import queue
import subprocess
import sys
import tempfile
import threading
import json
from typing import Callable, Dict, Any

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, ProgressBar, RichLog


class ProgressWidget(Widget):
    """Виджет установки Qt: запускает install_worker, читает лог, показывает прогресс."""

    DEFAULT_CSS = "ProgressWidget { height: 100%; }"

    def __init__(
        self,
        config_dict: Dict[str, Any],
        worker_path: str,
        on_done: Callable[[bool], None],
    ) -> None:
        super().__init__()
        self._config_dict = config_dict
        self._worker_path = worker_path
        self._on_done = on_done

        self._log_queue: queue.Queue = queue.Queue()
        self._stop_reading = False
        self._install_process = None
        self._reader_thread = None
        self._log_timer = None
        self._completion_timer = None
        self._config_json_path: str = ""

    def compose(self) -> ComposeResult:
        yield Label("Установка Qt...", classes="title-label")
        yield ProgressBar(total=100, show_eta=True, id="install_progress")
        yield RichLog(highlight=True, markup=False, wrap=True, id="install_log")

    def on_mount(self) -> None:
        self._progress_bar = self.query_one("#install_progress", ProgressBar)
        self._rich_log = self.query_one("#install_log", RichLog)
        self._start_installation()

    # -------------------------------------------------------------------------
    # Запуск процесса
    # -------------------------------------------------------------------------

    def _start_installation(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self._config_dict, f)
            self._config_json_path = f.name

        self._install_process = subprocess.Popen(
            [sys.executable, self._worker_path, self._config_json_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            start_new_session=True,
        )

        self._stop_reading = False
        self._reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self._reader_thread.start()

        self._log_timer = self.set_interval(0.05, self._process_log_queue)
        self._completion_timer = self.set_interval(0.2, self._check_process_completion)

    # -------------------------------------------------------------------------
    # Чтение вывода процесса
    # -------------------------------------------------------------------------

    def _read_process_output(self) -> None:
        try:
            for line in iter(self._install_process.stdout.readline, ""):
                if self._stop_reading:
                    break
                self._log_queue.put(line)
        except Exception as e:
            self._log_queue.put(f"ERROR reading output: {e}\n")
        finally:
            self._log_queue.put(None)

    def _process_log_queue(self) -> None:
        try:
            while True:
                line = self._log_queue.get_nowait()
                if line is None:
                    self._log_timer.stop()
                    break
                self._handle_log_line(line)
        except queue.Empty:
            pass

    def _handle_log_line(self, line: str) -> None:
        clean = line.strip()
        if not clean:
            return
        self._rich_log.write(clean)
        if "Downloading" in clean or "Extracting" in clean or "Finished" in clean:
            if self._progress_bar.total and self._progress_bar.progress < self._progress_bar.total:
                self._progress_bar.advance(1)
        if "===TOTAL_PACKAGES:" in clean:
            try:
                total_pkgs = int(clean.split(":")[1].replace("===", ""))
                self._progress_bar.total = total_pkgs * 2
                self._progress_bar.update(progress=0)
            except ValueError:
                pass

    # -------------------------------------------------------------------------
    # Завершение процесса
    # -------------------------------------------------------------------------

    def _check_process_completion(self) -> None:
        if self._install_process.poll() is not None:
            self._completion_timer.stop()
            self.set_timer(0.5, self._finish_installation)

    def on_unmount(self) -> None:
        self._stop_reading = True
        if self._log_timer:
            self._log_timer.stop()
        if self._completion_timer:
            self._completion_timer.stop()
        if self._install_process and self._install_process.poll() is None:
            self._install_process.terminate()
            try:
                self._install_process.wait(timeout=3)
                self.app.notify("Установка прервана", severity="warning")
            except subprocess.TimeoutExpired:
                self._install_process.kill()
                self.app.notify("Установка принудительно остановлена", severity="error")
        if self._config_json_path:
            try:
                os.unlink(self._config_json_path)
            except OSError:
                pass

    def _finish_installation(self) -> None:
        self._stop_reading = True
        if self._log_timer:
            self._log_timer.stop()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        self._install_process.stdout.close()
        exit_code = self._install_process.wait()
        try:
            os.unlink(self._config_json_path)
        except OSError:
            pass
        success = exit_code == 0
        if success:
            self._rich_log.write("\n[green]Установка успешно завершена![/]")
            self.notify("Установка Qt завершена успешно", severity="information")
        else:
            self._rich_log.write(f"\n[red]Ошибка установки: процесс завершился с кодом {exit_code}[/]")
            self.notify(f"Ошибка установки: код {exit_code}", severity="error")
        # через 5 секунд передаём управление обратно в App
        self.set_timer(5.0, lambda: self._on_done(success))
