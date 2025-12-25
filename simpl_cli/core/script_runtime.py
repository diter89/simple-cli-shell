#!/usr/bin/env python3
import code
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Optional
from rich import print
from ..ui.theme import PanelTheme


class ScriptRuntime:
    def __init__(self, console) -> None:
        self.console = console

        self._locals: dict[str, object] = {}
        self._interpreter = code.InteractiveConsole(locals=self._locals)
        self._active = False
        self._awaiting_more = False
        self._continuation_indent = ""

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def awaiting_more_input(self) -> bool:
        return self._awaiting_more

    @property
    def continuation_indent(self) -> str:
        return self._continuation_indent

    def activate(self) -> None:
        if not self._active:
            self._active = True
            self._awaiting_more = False
            self.console.print(
                PanelTheme.build(
                    "Script mode enabled. Type Python code or 'py exit' to leave.",
                    title="Script",
                    style="info",
                    fit=True,
                )
            )

    def deactivate(self, announce: bool = True) -> None:
        if self._active:
            self._active = False
            self._awaiting_more = False
            self._interpreter.resetbuffer()
            if announce:
                self.console.print(
                    PanelTheme.build(
                        "Script mode disabled.",
                        title="Script",
                        style="info",
                        fit=True,
                    )
                )

    def reset(self) -> None:
        self._locals.clear()
        self._interpreter = code.InteractiveConsole(locals=self._locals)
        self._awaiting_more = False
        self.console.print(
            PanelTheme.build(
                "Script state cleared.",
                title="Script",
                style="warning",
                fit=True,
            )
        )

    def run_inline(self, source: str) -> None:
        previously_active = self._active
        if not previously_active:
            self._active = True
        try:
            more = self._push(source)
            if more:
                self._awaiting_more = True
        finally:
            if not previously_active:
                self._active = False

    def run_line(self, source: str) -> None:
        if not self._active:
            self.activate()

        if self._awaiting_more and not source.strip():
            self._push("")
            return

        self._push(source)

    def cancel_pending_block(self) -> None:
        if not self._awaiting_more:
            return

        self._interpreter.resetbuffer()
        self._awaiting_more = False
        self._continuation_indent = ""
        print("[dim]Pending Python block cancelled.[/dim]")

    def _push(self, source: str) -> bool:
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        needs_more = False

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                needs_more = self._interpreter.push(source)
        except SystemExit:
            print(
                PanelTheme.build(
                    "SystemExit ignored inside script mode.",
                    title="Script",
                    style="warning",
                    fit=True,
                )
            )
            needs_more = False
        except Exception as e:
            print(f"[red]Unexpected error in script execution: {e}[/red]")
            import traceback

            print(f"[dim]{traceback.format_exc()}[/dim]")
            needs_more = False
        finally:
            stdout_value = stdout_capture.getvalue()
            stderr_value = stderr_capture.getvalue()

            if stdout_value:
                lines = stdout_value.split("\n")
                for line in lines:
                    if line.strip():
                        print(line)

            if stderr_value:
                self._format_and_print_stderr(stderr_value)

        self._awaiting_more = needs_more
        self._update_continuation_indent(source, needs_more)
        return needs_more

    def _format_and_print_stderr(self, stderr_text: str) -> None:
        if not stderr_text.strip():
            return

        lines = stderr_text.strip().split("\n")

        if len(lines) > 0 and "Traceback" in lines[0]:
            print("[bold red]Traceback (most recent call last):[/bold red]")

            for line in lines[1:-1]:
                if line.strip():
                    print(f"[dim]{line}[/dim]")

            if lines[-1].strip():
                last_line = lines[-1].strip()
                if ":" in last_line:
                    parts = last_line.split(":", 1)
                    if len(parts) == 2:
                        error_type, error_msg = parts
                        print(
                            f"[bold red]{error_type.strip()}:[/bold red] {error_msg.strip()}"
                        )
                    else:
                        print(f"[red]{last_line}[/red]")
                else:
                    print(f"[red]{last_line}[/red]")
        elif len(lines) > 0 and (
            "Error" in lines[-1].lower() or "Exception" in lines[-1].lower()
        ):
            print(f"[red]{stderr_text}[/red]")
        else:
            print(f"[yellow]{stderr_text}[/yellow]")

    def _update_continuation_indent(self, source: str, needs_more: bool) -> None:
        if not needs_more:
            self._continuation_indent = ""
            return

        stripped = source.lstrip()
        leading = source[: len(source) - len(stripped)]

        if stripped.endswith(":") or stripped.endswith("\\"):
            leading += "    "

        self._continuation_indent = leading
