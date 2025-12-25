#!/usr/bin/env python3
import os
from datetime import datetime
import subprocess
from typing import Callable, Iterable, List, Mapping, Tuple, Union
import psutil
import time

from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text import (
    FormattedText,
    HTML,
    fragment_list_width,
    merge_formatted_text,
    to_formatted_text,
)
from prompt_toolkit.styles import Style, merge_styles
from prompt_toolkit.styles.defaults import default_pygments_style, default_ui_style
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.status import Status
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..config import Config
from ..environment import (
    get_all_env_info,
    get_prompt_env_indicators,
)
from .theme import PanelTheme

import os

DEBUG_PLUGINS = os.environ.get("SIMPLE_CLI_DEBUG_PLUGINS", "0") == "1"

HAS_PLUGIN_SYSTEM = False
get_plugin_output = None

try:
    from .plugin_system import get_plugin_output as _get_plugin_output

    HAS_PLUGIN_SYSTEM = True
    get_plugin_output = _get_plugin_output
    if DEBUG_PLUGINS:
        print(f"[DEBUG] Loaded plugin system from .plugin_system")
except ImportError as e:
    if DEBUG_PLUGINS:
        print(f"[DEBUG] Failed to import from .plugin_system: {e}")

    try:
        from .simple_plugins import get_plugin_output as _get_plugin_output

        HAS_PLUGIN_SYSTEM = True
        get_plugin_output = _get_plugin_output
        if DEBUG_PLUGINS:
            print(f"[DEBUG] Loaded plugin system from .simple_plugins")
    except ImportError as e2:
        if DEBUG_PLUGINS:
            print(f"[DEBUG] Failed to import from .simple_plugins: {e2}")

        try:
            import sys
            from pathlib import Path
            import importlib.util

            home_plugins = Path.home() / ".simple_cli" / "quick_plugins.py"
            if home_plugins.exists():
                spec = importlib.util.spec_from_file_location(
                    "quick_plugins", home_plugins
                )
                if spec and spec.loader:
                    quick_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(quick_module)
                    get_plugin_output = quick_module.get_plugin_values
                    HAS_PLUGIN_SYSTEM = True
                    if DEBUG_PLUGINS:
                        print(f"[DEBUG] Loaded plugin system from {home_plugins}")
        except Exception as e3:
            if DEBUG_PLUGINS:
                print(f"[DEBUG] Failed to load quick plugins: {e3}")
            HAS_PLUGIN_SYSTEM = False


class UIManager:
    PromptPluginSegment = Union[str, Tuple[str, str], Mapping[str, object]]
    prompt_plugins: List[Callable[[], Iterable[PromptPluginSegment]]] = []

    @classmethod
    def has_plugin_system(cls):
        return HAS_PLUGIN_SYSTEM

    @classmethod
    def register_prompt_plugin(
        cls, plugin: Callable[[], Iterable[PromptPluginSegment]]
    ) -> None:
        if plugin not in cls.prompt_plugins:
            cls.prompt_plugins.append(plugin)

    @classmethod
    def unregister_prompt_plugin(
        cls, plugin: Callable[[], Iterable[PromptPluginSegment]]
    ) -> None:
        try:
            cls.prompt_plugins.remove(plugin)
        except ValueError:
            pass

    def __init__(self, console: Console) -> None:
        self.console = console
        self._pending_footer = None

    def get_prompt_text(self, mode: str) -> FormattedText:
        os_icon = "" if os.name != "nt" else ""
        folder_icon = ""

        path_display = self._format_path_for_prompt(os.getcwd())

        env_segments = []
        for style_name, text in get_prompt_env_indicators():
            tag = (
                style_name.split(":", 1)[1]
                if style_name.startswith("class:")
                else style_name
            )
            env_segments.append(f"<{tag}>{text}</{tag}>")

        plugin_values: dict[str, str] = {}

        if HAS_PLUGIN_SYSTEM:
            try:
                if callable(get_plugin_output):
                    result = get_plugin_output()
                    if DEBUG_PLUGINS:
                        print(f"[DEBUG] get_plugin_output() returned: {type(result)}")
                    if isinstance(result, dict):
                        plugin_values.update(result)
                        if DEBUG_PLUGINS:
                            print(f"[DEBUG] Plugin values: {plugin_values}")
                    elif isinstance(result, list):
                        for segment in result:
                            if isinstance(segment, dict) and "values" in segment:
                                extra_values = segment["values"]
                                if isinstance(extra_values, dict):
                                    for key, value in extra_values.items():
                                        plugin_values[str(key)] = str(value)
                                    if DEBUG_PLUGINS:
                                        print(
                                            f"[DEBUG] Plugin values from list: {plugin_values}"
                                        )
            except Exception as e:
                if DEBUG_PLUGINS:
                    print(f"[DEBUG] Error in get_plugin_output(): {e}")

                pass
        else:
            for plugin in self.prompt_plugins:
                try:
                    for segment in plugin():
                        if isinstance(segment, Mapping):
                            extra_values = (
                                segment.get("values") if "values" in segment else None
                            )
                            if isinstance(extra_values, Mapping):
                                for key, value in extra_values.items():
                                    plugin_values[str(key)] = str(value)

                            payload = (
                                segment.get("segment") if "segment" in segment else None
                            )
                            if payload is None:
                                continue
                            segment = payload

                        if isinstance(segment, tuple) and len(segment) == 2:
                            tag, text = segment
                            env_segments.append(f"<{tag}>{text}</{tag}>")
                        elif isinstance(segment, str):
                            env_segments.append(segment)
                except Exception:
                    continue

        env_html_str = " ".join(env_segments)

        template_top = getattr(Config, "PROMPT_TEMPLATE_TOP", "")
        template_bottom = getattr(Config, "PROMPT_TEMPLATE_BOTTOM", "")
        prompt_symbol_text = getattr(Config, "PROMPT_SYMBOL", "❯") or "❯"

        values = {
            "os_icon": os_icon,
            "folder_icon": folder_icon,
            "cwd": path_display,
            "env": env_html_str,
        }

        if plugin_values:
            values.update(plugin_values)

        if template_top or template_bottom:
            rendered_top = ""
            rendered_bottom = ""

            class _SafeDict(dict):
                def __missing__(self, key):
                    return ""

            safe_values = _SafeDict(values)
            try:
                if template_top:
                    rendered_top = template_top.format_map(safe_values)
                if template_bottom:
                    rendered_bottom = template_bottom.format_map(safe_values)
            except Exception:
                rendered_top = ""
                rendered_bottom = ""

            parts: list[FormattedText] = []
            if rendered_top:
                parts.append(HTML(rendered_top))
                parts.append("\n")

            bottom_core = rendered_bottom or "<prompt_border>╰─</prompt_border>"
            bottom_full = (
                f"{bottom_core}<prompt_symbol>{prompt_symbol_text}</prompt_symbol> "
            )
            parts.append(HTML(bottom_full))

            return merge_formatted_text(parts)

        env_html_str = f" {env_html_str}" if env_html_str else ""

        top_left_str = (
            "<prompt_border>╭─</prompt_border> "
            f"<prompt_os>{os_icon}</prompt_os> "
            f"<prompt_folder>{folder_icon}</prompt_folder> "
            f"<path>{path_display}</path>"
        )

        top_left_html = HTML(top_left_str)
        top_left_ft = to_formatted_text(top_left_html)

        env_html = HTML(env_html_str) if env_html_str else None
        env_ft = to_formatted_text(env_html) if env_html else []

        try:
            total_width = get_app().output.get_size().columns
        except Exception:
            total_width = 100

        used_width = fragment_list_width(top_left_ft) + (
            fragment_list_width(env_ft) if env_html else 0
        )
        padding_calc = total_width - used_width
        if env_html:
            padding_width = (
                padding_calc if padding_calc > 0 else 1 if padding_calc == 0 else 0
            )
        else:
            padding_width = padding_calc if padding_calc > 0 else 0
        padding_html = HTML(f"<prompt_padding>{'─' * padding_width}</prompt_padding>")

        prompt_symbol = HTML(f"<prompt_symbol>{prompt_symbol_text}</prompt_symbol> ")
        bottom_html = HTML("<prompt_border>╰─</prompt_border>")

        parts = [top_left_html, padding_html]
        if env_html:
            parts.append(env_html)
        parts.extend(["\n", bottom_html, prompt_symbol])

        return merge_formatted_text(parts)

    def get_style(self) -> Style:
        environment_styles = {
            "env_python": "#99d1db bold",
            "env_git": "#ef9f76 bold",
            "env_node": "#cba6f7 bold",
            "env_docker": "#81c8be bold",
            "env_system": "#e5c890 bold",
        }

        combined_styles = {
            **Config.PROMPT_STYLES,
            **Config.COMPLETION_STYLES,
            **Config.LEXER_STYLES,
            **environment_styles,
        }
        custom_style = Style.from_dict(combined_styles)
        return merge_styles(
            [default_ui_style(), default_pygments_style(), custom_style]
        )

    def _format_path_for_prompt(self, path: str) -> str:
        try:
            current_path = os.path.abspath(path)
        except OSError:
            return path

        home_dir = os.path.expanduser("~")

        if current_path == home_dir:
            return "~"

        if current_path.startswith(home_dir):
            relative = current_path[len(home_dir) + 1 :]
            if not relative:
                return "~"

            parts = relative.split(os.sep)
            if len(parts) == 1:
                return f"~/{parts[0]}"

            return f"../../{parts[-1]}"

        return current_path

    def show_welcome(self) -> None:
        if not Config.SHOW_STARTUP_BANNER:
            return

        env_info = get_all_env_info()

        welcome_parts: List[str] = [Config.WELCOME_MESSAGE]

        env_summary: List[str] = []
        if env_info.get("python"):
            py_env = env_info["python"]
            env_summary.append(
                f"󰌠 Python: {py_env['display']} (v{py_env['python_version']})"
            )

        if env_info.get("git"):
            git_info = env_info["git"]
            status_indicator = "" if git_info.get("has_changes") else ""
            env_summary.append(f" Git: {git_info['branch']} {status_indicator}")

        if env_info.get("node"):
            node_info = env_info["node"]
            env_summary.append(f"󰎙 Node: {node_info['name']} (v{node_info['version']})")

        if env_info.get("docker"):
            docker_info = env_info["docker"]
            env_summary.append(f"󰡨 Docker: {docker_info['display']}")

        if env_summary:
            welcome_parts.append("\n\n Detected Environments:")
            welcome_parts.extend([f"  {item}" for item in env_summary])

        welcome_panel = PanelTheme.build(
            "\n".join(welcome_parts), style="info", fit=True
        )
        self.console.print(welcome_panel)
        self.console.print()
        if self._pending_footer:
            self.console.print(f"[dim]{self._pending_footer}[/dim]")
            self._pending_footer = None

    def show_help(self) -> None:
        keybindings_lines = ["[bold]Keybindings[/bold]"]
        for keybind, description in Config.HELP_KEYBINDS:
            keybindings_lines.append(f"  • [cyan]{keybind}[/cyan] – {description}")

        commands_lines = ["\n[bold]Special Commands[/bold]"]
        for command, mode, description in Config.HELP_SPECIAL_COMMANDS:
            commands_lines.append(
                f"  • [cyan]{command}[/cyan] ({mode}) – {description}"
            )
        commands_lines.extend(
            [
                "  • [cyan]/config_reload[/cyan] (Shell) – Reload configuration",
                "  • [cyan]/cleanup_memory[/cyan] (Shell) – Clean up caches and memory",
                "  • [cyan]/help[/cyan] (Shell) – Show this help",
            ]
        )

        env_lines = ["\n[bold]Environment Commands[/bold]"]
        env_lines.extend(
            [
                "  • [cyan]!env[/cyan] – Show current environment status",
                "  • [cyan]!status[/cyan] – Show detailed system and environment info",
                "  • [cyan]!git[/cyan] – Show git repository information",
                "  • [cyan]!python[/cyan] – Show Python environment details",
            ]
        )

        help_text = "\n".join(keybindings_lines + commands_lines + env_lines)

        self.console.print()
        self.console.print(
            PanelTheme.build(help_text, title="Help", style="info", fit=True)
        )
        self.console.print()
        if self._pending_footer:
            self.console.print(f"[dim]{self._pending_footer}[/dim]")
            self._pending_footer = None

    def show_mode_switch(self, mode_name: str) -> None:

        return

    def show_context_cleared(self) -> None:
        self.console.print(
            PanelTheme.build(
                " Context cleared!",
                title="Cleared",
                style="success",
            )
        )
        if self._pending_footer:
            self.console.print(f"[dim]{self._pending_footer}[/dim]")
            self._pending_footer = None

    def show_context_table(self, shell_context: list) -> None:
        if not shell_context:
            self.console.print(
                PanelTheme.build(
                    "[yellow]No shell context available[/yellow]",
                    title="Shell Context",
                    style="warning",
                )
            )
            return

        context_table = Table(
            title="Shell Context", show_header=True, header_style="bold cyan"
        )
        context_table.add_column("Time", style="dim", no_wrap=True)
        context_table.add_column("Command", style="cyan")
        context_table.add_column("Directory", style="yellow", no_wrap=True)
        context_table.add_column("Output Preview", style="white")

        for entry in shell_context[-Config.MAX_SHELL_CONTEXT :]:
            output_preview = (
                entry["output"][:50] + "..."
                if len(entry["output"]) > 50
                else entry["output"]
            )
            output_preview = output_preview.replace("\n", " ")

            context_table.add_row(
                entry["timestamp"],
                entry["command"],
                entry["cwd"].split("/")[-1],
                output_preview,
            )

        self.console.print(
            PanelTheme.build(context_table, title="Shell Context", style="info")
        )

    def display_shell_output(self, command: str, result) -> None:
        base_cmd = command.strip().split()[0]
        if self._should_use_ls_table(command, base_cmd):
            self._display_ls_table(command, result)
            if self._pending_footer:
                self.console.print(f"[dim]{self._pending_footer}[/dim]")
                self._pending_footer = None
            return

        output = result.stdout + result.stderr

        if result.stdout and result.stderr:
            combined_output = Text()
            if result.stdout:
                combined_output.append(result.stdout, style="white")
            if result.stderr:
                combined_output.append(result.stderr, style="red")

            self.console.print(
                PanelTheme.build(
                    combined_output,
                    title=f" Shell: {command}",
                    style="default",
                    fit=True,
                )
            )
        elif result.stdout:
            syntax_content = self._try_syntax_highlighting(command, result.stdout)
            self.console.print(
                PanelTheme.build(
                    syntax_content,
                    title=f" Shell: {command}",
                    style="default",
                    fit=True,
                )
            )
        elif result.stderr:
            self.console.print(
                PanelTheme.build(
                    f"[red]{result.stderr}[/red]",
                    title=f" Shell: {command}",
                    style="error",
                    fit=True,
                )
            )
        else:
            self.console.print(
                PanelTheme.build(
                    "[dim]No output[/dim]",
                    title=f" Shell: {command}",
                    style="default",
                    fit=True,
                )
            )

        if self._pending_footer:
            self.console.print(f"[dim]{self._pending_footer}[/dim]")
            self._pending_footer = None

    def _should_use_ls_table(self, command: str, base_cmd: str) -> bool:
        if any(op in command for op in ["|", ">", "<", "2>", "&>", "&&", "||", ";"]):
            return False

        if base_cmd in Config.LS_COMMANDS:
            return True

        if base_cmd == "ls" or command.startswith("ls "):
            return True

        return False

    def _display_ls_table(self, command: str, result) -> None:
        if result.returncode != 0:
            self.console.print(
                PanelTheme.build(
                    f"[red]{result.stderr}[/red]",
                    title=f" Shell: {command}",
                    style="error",
                )
            )
            return

        if not result.stdout.strip():
            self.console.print(
                PanelTheme.build(
                    "[yellow]Directory is empty[/yellow]",
                    title=f" Directory Listing: {command}",
                    style="warning",
                )
            )
            return

        try:
            ls_table = self._create_ls_table(command, result.stdout)
            self.console.print(
                PanelTheme.build(
                    ls_table,
                    title=f" Directory Listing: {command}",
                    style="info",
                    fit=True,
                    padding=(1, 2),
                )
            )
        except Exception:
            self.console.print(
                PanelTheme.build(
                    result.stdout,
                    title=f" Shell: {command}",
                    style="default",
                )
            )

    def _create_ls_table(self, command: str, ls_output: str) -> Table:
        table = Table(show_header=True, header_style="bold cyan", box=None)

        lines = ls_output.strip().split("\n")
        has_details = self._is_detailed_listing(lines, command)

        if has_details:
            table.add_column("Permissions", style="dim")
            table.add_column("Links", style="dim", justify="right")
            table.add_column("Owner", style="dim")
            table.add_column("Group", style="dim")
            table.add_column("Size", style="cyan", justify="right")
            table.add_column("Date", style="yellow")
            table.add_column("Name", style="bold")
        else:
            table.add_column("Type", justify="center", width=4)
            table.add_column("Name", style="bold")
            table.add_column("Size", style="cyan", justify="right")
            table.add_column("Modified", style="yellow")

        target_dir = self._extract_target_directory(command)
        for line in lines:
            line = line.strip()
            if not line or line.startswith("total "):
                continue

            try:
                if has_details:
                    self._add_detailed_row(table, line, target_dir)
                else:
                    self._add_simple_row(table, line, target_dir)
            except Exception:
                continue

        return table

    def _is_detailed_listing(self, lines: list, command: str) -> bool:
        if "-l" in command:
            return True

        detailed_patterns = 0
        for line in lines[:5]:
            line = line.strip()
            if not line or line.startswith("total"):
                continue

            parts = line.split()
            if len(parts) >= 8:
                first_part = parts[0]
                if (
                    len(first_part) == 10
                    and first_part[0] in "-dlbcsp"
                    and all(c in "rwx-" for c in first_part[1:])
                ):
                    detailed_patterns += 1

        non_empty_lines = len(
            [l for l in lines if l.strip() and not l.startswith("total")]
        )
        return (
            detailed_patterns > 0
            and (detailed_patterns / max(non_empty_lines, 1)) > 0.5
        )

    def _extract_target_directory(self, command: str) -> str:
        parts = command.split()
        for part in parts[1:]:
            if not part.startswith("-"):
                if os.path.isabs(part):
                    return part
                return os.path.join(os.getcwd(), part)

        return os.getcwd()

    def _add_detailed_row(self, table: Table, line: str, current_dir: str) -> None:
        import re

        cleaned_line = line
        parts = cleaned_line.split()
        if len(parts) < 8:
            return

        permissions = parts[0]
        links = parts[1]
        owner = parts[2]
        group = parts[3]
        size = parts[4]

        month_abbrevs = {
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        }

        month_idx = -1
        for i in range(5, len(parts)):
            if parts[i] in month_abbrevs:
                month_idx = i
                break

        if month_idx == -1:
            if len(parts) >= 9:
                date_parts = parts[5:8]
                name = " ".join(parts[8:])
            else:
                date_parts = parts[5:7]
                name = " ".join(parts[7:])
        else:
            date_parts = []
            idx = month_idx

            date_parts.append(parts[idx])
            idx += 1

            if idx < len(parts) and parts[idx].isdigit() and 1 <= int(parts[idx]) <= 31:
                date_parts.append(parts[idx])
                idx += 1

            while idx < len(parts):
                part = parts[idx]
                if ":" in part:  # Time format
                    date_parts.append(part)
                    idx += 1
                    break
                elif part.isdigit() and len(part) == 4:  # Year
                    date_parts.append(part)
                    idx += 1
                    break
                else:
                    idx += 1

            name_parts = parts[idx:] if idx < len(parts) else []

            cleaned_name_parts = []
            for part in name_parts:
                if part in {"*", "/", "=", "@", "|"}:
                    continue
                if (
                    len(part) == 1
                    and not part.isalnum()
                    and not part in {".", "-", "_"}
                ):
                    continue
                cleaned_name_parts.append(part)

            name = " ".join(cleaned_name_parts) if cleaned_name_parts else "."

        date_str = " ".join(date_parts)

        actual_name = name
        for sym in ["*", "/", "=", "@", "|"]:
            if actual_name.endswith(sym):
                actual_name = actual_name[:-1]

        _, icon, color = self._get_file_info(actual_name, current_dir, permissions)
        formatted_size = self._format_size(size) if size.isdigit() else size

        table.add_row(
            f"[dim]{permissions}[/dim]",
            f"[dim]{links}[/dim]",
            f"[dim]{owner}[/dim]",
            f"[dim]{group}[/dim]",
            f"[cyan]{formatted_size}[/cyan]",
            f"[yellow]{date_str}[/yellow]",
            f"[{color}]{icon} {name}[/{color}]",
        )

    def _add_simple_row(self, table: Table, filename: str, current_dir: str) -> None:
        file_path = os.path.join(current_dir, filename)
        _, icon, color = self._get_file_info(filename, current_dir)

        size = "-"
        mtime = "?"

        try:
            if os.path.exists(file_path):
                stat_info = os.stat(file_path)
                if not os.path.isdir(file_path):
                    size = self._format_size(stat_info.st_size)
                else:
                    size = "-"
                mtime = datetime.fromtimestamp(stat_info.st_mtime).strftime(
                    "%b %d %H:%M"
                )
        except (OSError, PermissionError, FileNotFoundError):
            size = "?"
            mtime = "?"

        table.add_row(
            f"[{color}]{icon}[/{color}]",
            f"[{color}]{filename}[/{color}]",
            f"[cyan]{size}[/cyan]",
            f"[yellow]{mtime}[/yellow]",
        )

    def _get_file_info(
        self, filename: str, current_dir: str, permissions: str | None = None
    ):
        file_path = os.path.join(current_dir, filename)

        is_hidden = filename.startswith(".")

        try:
            if permissions:
                if permissions.startswith("d"):
                    file_type = "directory"
                elif permissions.startswith("l"):
                    file_type = "symlink"
                elif "x" in permissions:
                    file_type = "executable"
                else:
                    file_type = self._get_file_type_by_extension(filename)
            elif os.path.exists(file_path):
                if os.path.isdir(file_path):
                    file_type = "directory"
                elif os.path.islink(file_path):
                    file_type = "symlink"
                elif os.access(file_path, os.X_OK) and not os.path.isdir(file_path):
                    file_type = "executable"
                else:
                    file_type = self._get_file_type_by_extension(filename)
            else:
                alt_path = os.path.join(os.getcwd(), filename)
                if current_dir != os.getcwd() and os.path.exists(alt_path):
                    if os.path.isdir(alt_path):
                        file_type = "directory"
                    elif os.path.islink(alt_path):
                        file_type = "symlink"
                    elif os.access(alt_path, os.X_OK):
                        file_type = "executable"
                    else:
                        file_type = self._get_file_type_by_extension(filename)
                else:
                    file_type = self._get_file_type_by_extension(filename)
        except (OSError, PermissionError):
            file_type = self._get_file_type_by_extension(filename)

        icon = Config.FILE_ICONS.get(file_type, Config.FILE_ICONS["file"])
        color_key = "hidden" if is_hidden else file_type
        color = Config.FILE_COLORS.get(color_key, Config.FILE_COLORS["file"])
        return file_type, icon, color

    def _get_file_type_by_extension(self, filename: str) -> str:
        if not filename or (filename.startswith(".") and "." not in filename[1:]):
            return "file"

        ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
        return Config.FILE_EXTENSIONS.get(ext, "file")

    def _format_size(self, size_bytes) -> str:
        try:
            size_bytes = int(size_bytes)
        except (ValueError, TypeError):
            return str(size_bytes)

        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        if i == 0:
            return f"{size_bytes} {size_names[i]}"
        return f"{size_bytes:.1f} {size_names[i]}"

    def _try_syntax_highlighting(self, command: str, output: str):
        base_cmd = command.split()[0]
        if base_cmd not in Config.SYNTAX_HIGHLIGHT_COMMANDS:
            return output

        for ext, lang in Config.SYNTAX_EXTENSIONS.items():
            if ext in command:
                try:
                    return Syntax(
                        output,
                        lang,
                        theme=Config.SYNTAX_THEME,
                        line_numbers=True,
                        indent_guides=True,
                    )
                except Exception:
                    break

        return output

    def display_directory_change(self, command: str, new_dir: str) -> None:
        self.console.print(
            PanelTheme.build(
                f"[green]Changed directory to: {new_dir}[/green]",
                title=f" Shell: {command}",
                style="default",
                fit=True,
                highlight=True,
            )
        )

    def display_file_explorer(
        self,
        base_path: str,
        directories: list[dict],
        files: list[dict],
        preview: dict | None,
        dir_total: int,
        file_total: int,
        show_hidden: bool,
    ) -> None:
        dir_table = Table(
            title="Directories", show_header=True, header_style="bold cyan"
        )
        dir_table.add_column("Name", style="bold")
        dir_table.add_column("Modified", style="yellow")

        if directories:
            for entry in directories:
                _, icon, color = self._get_file_info(entry["name"], base_path)
                dir_table.add_row(
                    f"[{color}]{icon} {entry['name']}[/{color}]",
                    entry["mtime"],
                )
        else:
            dir_table.add_row("[dim]No directories to display[/dim]", "-")

        file_table = Table(title="Files", show_header=True, header_style="bold cyan")
        file_table.add_column("Name", style="bold")
        file_table.add_column("Size", justify="right", style="cyan")
        file_table.add_column("Modified", style="yellow")

        if files:
            for entry in files:
                _, icon, color = self._get_file_info(entry["name"], base_path)
                file_table.add_row(
                    f"[{color}]{icon} {entry['name']}[/{color}]",
                    self._format_size(entry["size"]),
                    entry["mtime"],
                )
        else:
            file_table.add_row("[dim]No files to display[/dim]", "-", "-")

        tables = [
            PanelTheme.build(
                dir_table, title=f" Directories ({dir_total})", style="info", fit=True
            )
        ]
        tables.append(
            PanelTheme.build(
                file_table, title=f" Files ({file_total})", style="info", fit=True
            )
        )

        if preview:
            preview_title = (
                os.path.basename(preview.get("path", base_path))
                if preview.get("path")
                else "Preview"
            )
            preview_renderable = self._build_preview_renderable(preview)
            tables.append(
                PanelTheme.build(
                    preview_renderable,
                    title=f" Preview: {preview_title}",
                    style="default",
                    fit=True,
                )
            )

        summary = f"Path: {base_path}"
        if show_hidden:
            summary += " • showing hidden"

        self.console.print(
            PanelTheme.build(summary, style="default", title="File Explorer", fit=True)
        )
        self.console.print(Columns(tables, equal=True, expand=True))

    def display_error(self, command: str, error_msg: str) -> None:
        import re

        shell_error_pattern = r"^([^:]+):\s*line\s*(\d+):\s*([^:]+):\s*(.+)$"
        match = re.match(shell_error_pattern, error_msg.strip())

        if match:
            shell_path, line_num, error_source, error_detail = match.groups()
            tree = Tree("[bold red]Shell Error[/bold red]")
            tree.add(f"[cyan]Input:[/cyan] {command}")

            shell_info = tree.add("[yellow]Shell Information[/yellow]")
            shell_info.add(f"[dim]Shell:[/dim] {shell_path}")
            shell_info.add(f"[dim]Line:[/dim] {line_num}")

            error_node = tree.add("[red]Error Details[/red]")
            error_node.add(f"[bold]Source:[/bold] {error_source}")
            error_node.add(f"[bold]Message:[/bold] {error_detail}")

            tips_node = tree.add("[green]Tips[/green]")
            tips_node.add("• Check for syntax errors in the command")
            tips_node.add("• Verify file paths and permissions")
            tips_node.add("• Ensure proper quoting of special characters")

            self.console.print(
                PanelTheme.build(
                    tree,
                    title=f" Shell: {command}",
                    style="error",
                    fit=True,
                )
            )
        else:
            if ":" in error_msg and (
                "error" in error_msg.lower() or "failed" in error_msg.lower()
            ):
                tree = Tree("[bold red]Error[/bold red]")
                tree.add(f"[cyan]Command:[/cyan] {command}")
                tree.add(f"[red]Message:[/red] {error_msg}")

                tips_node = tree.add("[green]Suggestions[/green]")
                tips_node.add("• Review the command syntax")
                tips_node.add("• Check for missing arguments or options")
                tips_node.add("• Verify dependencies and permissions")

                self.console.print(
                    PanelTheme.build(
                        tree,
                        title=f" Shell: {command}",
                        style="error",
                        fit=True,
                    )
                )
            else:
                self.console.print(
                    PanelTheme.build(
                        f"[red]{error_msg}[/red]",
                        title=f" Shell: {command}",
                        style="error",
                        fit=True,
                    )
                )

    def display_command_not_found(
        self,
        command: str,
        base_command: str,
        error_text: str,
        suggestions: List[str],
    ) -> None:
        error_message = error_text.strip() or "command not found"
        tree = Tree("[bold red]Command Not Found[/bold red]")
        tree.add(f"[cyan]Input:[/cyan] {command}")

        shell_node = tree.add("[yellow]Shell response[/yellow]")
        shell_node.add(f"[red]{error_message}[/red]")

        tips_node = tree.add("[green]Tips[/green]")
        tips_node.add(
            f"• Ensure '[bold]{base_command or command}[/bold]' exists on your system or is available in PATH"
        )
        tips_node.add(
            "• Double-check for typos or run 'which <command>' to verify availability"
        )
        tips_node.add("• Use '/help' to see available internal commands")

        if suggestions:
            suggestion_node = tree.add("[cyan]Possible similar commands[/cyan]")
            for suggestion in suggestions:
                suggestion_node.add(f"- {suggestion}")

        self.console.print(
            PanelTheme.build(
                tree,
                title=f" Shell: {command}",
                style="error",
                fit=True,
            )
        )

    def _build_preview_renderable(self, preview: dict):
        error_msg = preview.get("error")
        if error_msg:
            return Text(f"Error: {error_msg}", style="red")

        content = preview.get("content", "")
        language = preview.get("language", "text")

        if language and language != "text":
            try:
                return Syntax(
                    content,
                    language,
                    theme=Config.SYNTAX_THEME,
                    line_numbers=True,
                    indent_guides=True,
                )
            except Exception:
                return Text(content, overflow="fold")

        return Text(content, overflow="fold")

    def display_interactive_start(self, command: str) -> None:
        return

    def display_interactive_end(self, command: str, return_code: int) -> None:
        if self._pending_footer:
            self.console.print(f"[dim]{self._pending_footer}[/dim]")
            self._pending_footer = None

    def display_interrupt(self, message: str = "^C - Command interrupted") -> None:
        self.console.print(
            PanelTheme.build(
                f"[yellow]{message}[/yellow]",
                title=" Shell",
                style="warning",
                fit=True,
            )
        )

    def display_goodbye(self) -> None:
        self.console.print("[yellow]Goodbye![/yellow]")

    def create_status(self, message: str) -> Status:
        return Status(f"[bold green]{message}", console=self.console)

    @staticmethod
    def create_progress_bar(description: str) -> Progress:
        progress = Progress(
            SpinnerColumn("point"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            transient=False,
        )
        progress.add_task(description, total=None)
        return progress

    def render_markdown(self, content: str):
        try:
            return Markdown(content)
        except Exception:
            return Text(content, overflow="fold")
