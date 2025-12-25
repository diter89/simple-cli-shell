#!/usr/bin/env python3
import os
import select
import subprocess
import sys
import signal

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.text import Text

from .theme import PanelTheme
from ..config import Config


class ShellLiveStreamRenderer:
    def __init__(self, max_visible_lines: int = 15) -> None:
        self.max_visible_lines = max_visible_lines
        self.lines: list[str] = []
        self.current_line: str = ""
        self.full_content: str = ""

    def reset(self) -> None:
        self.lines = []
        self.current_line = ""
        self.full_content = ""

    def add_chunk(self, chunk: str) -> None:
        if not chunk:
            return

        normalized = chunk.replace("\r\n", "\n").replace("\r", "\n")
        self.full_content += normalized

        composed = self.current_line + normalized
        parts = composed.split("\n")
        self.lines.extend(parts[:-1])
        self.current_line = parts[-1]

        if len(self.lines) > self.max_visible_lines:
            self.lines = self.lines[-self.max_visible_lines :]

    def get_renderable(self) -> Text:
        display_lines = self.lines[-self.max_visible_lines :].copy()
        if self.current_line:
            display_lines.append(self.current_line)

        if not display_lines:
            return Text(" Waiting for output...", overflow="fold")

        return Text("\n".join(display_lines), overflow="fold")

    def get_full_output(self) -> str:
        return self.full_content


class StreamingUIManager:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.shell_renderer = ShellLiveStreamRenderer()

    def stream_shell_command(self, command: str, process: subprocess.Popen):
        if process.stdout is None:
            exit_code = process.wait()
            return "", exit_code, False

        renderer = self.shell_renderer
        renderer.reset()

        cancelled = False
        exit_code = None
        title_command = command if len(command) <= 60 else f"{command[:57]}..."

        stdout_fd = process.stdout.fileno()
        stdin_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        input_enabled = (
            stdin_fd is not None and process.stdin is not None and termios and tty
        )

        old_term_settings = None
        if input_enabled:
            old_term_settings = termios.tcgetattr(stdin_fd)
            tty.setcbreak(stdin_fd)

        final_output = ""

        final_output = ""
        final_title = " Shell Command - Complete"
        final_style = "success"

        try:
            with Live(console=self.console, refresh_per_second=12) as live:
                live.update(
                    PanelTheme.build(
                        Align.center(f"󰣸  Executing: '{title_command}'"),
                        title=" Shell Command",
                        style="info",
                        padding=(1, 2),
                        fit=True,
                        highlight=True,
                    )
                )

                while True:
                    watch_fds = [stdout_fd]
                    if input_enabled:
                        watch_fds.append(stdin_fd)

                    ready, _, _ = select.select(watch_fds, [], [], 0.1)

                    if stdout_fd in ready:
                        try:
                            chunk = os.read(stdout_fd, 4096)
                        except OSError:
                            chunk = b""

                        if not chunk:
                            if process.poll() is not None:
                                break
                        else:
                            text_chunk = chunk.decode("utf-8", errors="replace")
                            renderer.add_chunk(text_chunk)
                            live.update(
                                PanelTheme.build(
                                    renderer.get_renderable(),
                                    title=f" {title_command}",
                                    style="info",
                                    padding=(0, 1),
                                    fit=True,
                                    highlight=True,
                                )
                            )

                    if input_enabled and stdin_fd in ready and process.stdin:
                        try:
                            user_input = os.read(stdin_fd, 4096)
                        except OSError:
                            user_input = b""

                        if user_input:
                            if b"\x03" in user_input:
                                cancelled = True
                                try:
                                    process.send_signal(signal.SIGINT)
                                except Exception:
                                    process.terminate()
                                break
                            try:
                                process.stdin.write(user_input)
                                process.stdin.flush()
                            except Exception:
                                pass

                    if (
                        process.poll() is not None
                        and not select.select([stdout_fd], [], [], 0)[0]
                    ):
                        break

                try:
                    exit_code = process.wait(timeout=0.1)
                except Exception:
                    exit_code = process.poll()

                final_style = "success"
                if cancelled:
                    final_style = "warning"
                elif exit_code not in (0, None):
                    final_style = "error"

                final_title = " Shell Command - Complete"
                if cancelled:
                    final_title = " Shell Command - Cancelled"
                elif exit_code not in (0, None):
                    final_title = f" Shell Command - Exit {exit_code}"

                final_output = renderer.get_full_output()

                if Config.is_shell_stream_summary_enabled():
                    summary_lines = []
                    if cancelled:
                        summary_lines.append(
                            " Command cancelled. Partial output shown below."
                        )
                    else:
                        summary_lines.append(
                            f" Exit code: {exit_code if exit_code is not None else 'unknown'}"
                        )
                        if final_output:
                            summary_lines.append("Output printed below.")
                        else:
                            summary_lines.append("No output produced.")

                    summary_text = Align.left("\n".join(summary_lines))

                    live.update(
                        PanelTheme.build(
                            summary_text,
                            title=final_title,
                            style=final_style,
                            padding=(0, 1),
                            fit=True,
                            highlight=True,
                        )
                    )
                else:
                    live.update(
                        Align.left(
                            f"Command finished with exit code {exit_code if exit_code is not None else 'unknown'}"
                        )
                    )

        except KeyboardInterrupt:
            cancelled = True
            try:
                process.send_signal(signal.SIGINT)
            except Exception:
                try:
                    process.terminate()
                except Exception:
                    pass

        finally:
            if input_enabled and old_term_settings is not None:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_term_settings)

        if exit_code is None:
            try:
                exit_code = process.wait(timeout=1)
            except Exception:
                exit_code = process.poll()

        display_text: Text | None = None
        if final_output:
            display_text = Text(final_output, overflow="fold")
        elif not cancelled:
            display_text = Text("(no output)", style="dim")

        if display_text is not None:
            if Config.is_shell_stream_output_panel_enabled():
                self.console.print(
                    PanelTheme.build(
                        display_text,
                        title=final_title,
                        style=final_style,
                        padding=(0, 1),
                        fit=True,
                        highlight=True,
                    )
                )

            else:
                self.console.print(display_text)

        return renderer.get_full_output(), exit_code, cancelled
