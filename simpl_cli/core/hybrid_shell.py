#!/usr/bin/env python3
from typing import Optional
import os
import hashlib
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, AutoSuggest, Suggestion
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.layout.processors import Processor, Transformation

from ..commands import ShellCommandExecutor
from ..completion import create_completion_manager
from ..config import Config

from ..ui import StreamingUIManager, UIManager
from ..ui.highlighter import create_console
from ..ui.theme import PanelTheme

import re

try:
    from pygments.lexers import find_lexer_class_by_name
except ImportError:
    find_lexer_class_by_name = None


class DummyContextManager:

    def __init__(self):
        self.shell_context = []

    def add_shell_context(self, command: str, output: str) -> None:
        pass

    def clear_all(self) -> None:
        pass


class DirectoryFilteredAutoSuggest(AutoSuggest):

    def __init__(self, history: FileHistory, shell_instance=None):
        self.history = history
        self.shell = shell_instance

    def get_suggestion(self, buffer, document):
        current_text = document.text

        if not current_text.strip():
            return None

        try:
            history_strings = list(self.history.load_history_strings())
        except Exception:
            return None

        best_suggestion = None
        best_match_length = 0

        for history_str in history_strings:
            if not history_str or not history_str.strip():
                continue

            suggestion_text = self._get_suggestion_text(current_text, history_str)
            if suggestion_text is not None:
                if self._is_suggestion_valid(history_str):
                    if len(history_str) > best_match_length:
                        best_match_length = len(history_str)
                        best_suggestion = Suggestion(suggestion_text)

        return best_suggestion

    def _get_suggestion_text(self, current_text, history_str):
        if history_str.startswith(current_text):
            return history_str[len(current_text) :]

        if current_text and not current_text.endswith(" "):
            current_with_space = current_text + " "
            if history_str.startswith(current_with_space):
                return history_str[len(current_with_space) - 1 :]

        return None

    def _is_suggestion_valid(self, full_command):
        parts = full_command.strip().split()
        if not parts:
            return True

        command = parts[0].lower()
        file_commands = {
            "cd",
            "ls",
            "cat",
            "vim",
            "nano",
            "code",
            "cp",
            "mv",
            "rm",
            "mkdir",
        }

        if command not in file_commands:
            return True

        if len(parts) > 1:
            path_arg = parts[1]
            return self._is_path_valid_for_command(path_arg, command)

        return True

    def _is_path_valid_for_command(self, path, command):
        try:
            cwd = os.getcwd()
            if path.startswith("/"):
                check_path = path
            elif path.startswith("~"):
                check_path = os.path.expanduser(path)
            else:
                check_path = os.path.join(cwd, path)

            if not os.path.exists(check_path):
                return False

            if command == "cd":
                return os.path.isdir(check_path)

            return True
        except Exception:
            return False


class DirectoryIsolatedHistory(FileHistory):

    def __init__(self, base_history_dir=None):
        if base_history_dir is None:
            from ..config import Config

            base_history_dir = Config.CONFIG_DIR / "history"

        self.base_history_dir = Path(base_history_dir).expanduser()
        self.base_history_dir.mkdir(parents=True, exist_ok=True)
        self.current_history_file = None

        super().__init__(str(self.base_history_dir / ".default_history.txt"))

    def _get_directory_hash(self, directory_path):
        normalized_path = str(Path(directory_path).resolve())
        return hashlib.md5(normalized_path.encode()).hexdigest()[:12]

    def _get_history_file_for_directory(self, directory_path):
        dir_hash = self._get_directory_hash(directory_path)
        history_dir = self.base_history_dir / dir_hash
        history_dir.mkdir(exist_ok=True)
        return history_dir / "history.txt"

    def _ensure_correct_history_file(self):
        try:
            cwd = os.getcwd()
            new_history_file = self._get_history_file_for_directory(cwd)
            if self.current_history_file != new_history_file:
                self.current_history_file = new_history_file
                self.filename = str(self.current_history_file)
                if hasattr(self, "_loaded"):
                    self._loaded = False
                if hasattr(self, "_loaded_strings"):
                    self._loaded_strings = []
        except Exception:
            if (
                self.current_history_file
                != self.base_history_dir / ".default_history.txt"
            ):
                self.current_history_file = (
                    self.base_history_dir / ".default_history.txt"
                )
                self.filename = str(self.current_history_file)
                if hasattr(self, "_loaded"):
                    self._loaded = False
                if hasattr(self, "_loaded_strings"):
                    self._loaded_strings = []

    def load_history(self):
        self._ensure_correct_history_file()

    def store_string(self, string):
        self._ensure_correct_history_file()
        super().store_string(string)

    def get_strings(self):
        self._ensure_correct_history_file()
        return super().get_strings()

    def load_history_strings(self):
        self._ensure_correct_history_file()
        return super().load_history_strings()


class HybridShell:
    def __init__(self) -> None:
        self.mode = "shell"

        self.session = PromptSession(history=DirectoryIsolatedHistory())
        self.console = create_console()

        self.ui = UIManager(self.console)
        self.streaming_ui = StreamingUIManager(self.console)

        self.context_manager = DummyContextManager()

        self.completion_manager = create_completion_manager()
        self.command_executor = ShellCommandExecutor(
            console=self.console,
            ui=self.ui,
            streaming_ui=self.streaming_ui,
            context_manager=self.context_manager,
            completion_manager=self.completion_manager,
        )

        self._shell_buffer: list[str] = []
        self._shell_awaiting_more: bool = False

        self._setup_keybindings()

        self.prompt_lexer = self._create_prompt_lexer()
        self.command_highlight_processor = self._create_command_highlight_processor()
        self.path_highlight_processor = self._create_path_highlight_processor()

    def _create_command_highlight_processor(self):
        class CommandHighlightProcessor(Processor):
            def __init__(self, highlight_map):
                self.highlight_map = highlight_map

            def apply_transformation(self, transformation_input):
                document = transformation_input.document
                text = document.text

                if not text or not self.highlight_map:
                    return Transformation(transformation_input.fragments)

                commands_sorted = sorted(
                    self.highlight_map.items(), key=lambda x: len(x[0]), reverse=True
                )

                matches = []
                for command, style in commands_sorted:
                    if command.startswith("-"):
                        pattern = rf"(?:^|\s)({re.escape(command)})(?=\s|$)"
                    else:
                        pattern = rf"\b{re.escape(command)}\b"

                    for match in re.finditer(pattern, text):
                        if command.startswith("-"):
                            start, end = match.span(1)
                        else:
                            start, end = match.span()

                        overlap = False
                        for existing_start, existing_end, existing_style in matches:
                            if not (end <= existing_start or start >= existing_end):
                                overlap = True
                                break

                        if not overlap:
                            matches.append((start, end, style))

                matches.sort(key=lambda x: x[0])

                if not matches:
                    return Transformation(transformation_input.fragments)

                original_fragments = transformation_input.fragments
                new_fragments = []

                for fragment_style, fragment_text in original_fragments:
                    if (
                        "suggestion" in fragment_style
                        or "auto" in fragment_style
                        or "completion" in fragment_style
                    ):
                        new_fragments.append((fragment_style, fragment_text))
                    else:
                        current_pos = 0
                        fragment_modified = False

                        for start, end, match_style in matches:
                            if start >= len(fragment_text):
                                continue
                            if end > len(fragment_text):
                                end = len(fragment_text)

                            if start > current_pos:
                                plain_text = fragment_text[current_pos:start]
                                new_fragments.append((fragment_style, plain_text))

                            matched_text = fragment_text[start:end]
                            new_fragments.append((match_style, matched_text))

                            current_pos = end
                            fragment_modified = True

                        if current_pos < len(fragment_text):
                            plain_text = fragment_text[current_pos:]
                            new_fragments.append((fragment_style, plain_text))
                        elif not fragment_modified:
                            new_fragments.append((fragment_style, fragment_text))

                return Transformation(new_fragments)

        return CommandHighlightProcessor(Config.COMMAND_HIGHLIGHT)

    def _create_path_highlight_processor(self):

        class PathHighlightProcessor(Processor):
            def __init__(self, shell_instance):
                self.shell = shell_instance
                self.file_commands = {
                    "cd",
                    "pwd",
                    "cat",
                    "head",
                    "tail",
                    "less",
                    "more",
                    "bat",
                    "batcat",
                    "rm",
                    "mv",
                    "cp",
                    "ln",
                    "chmod",
                    "touch",
                    "ls",
                    "mkdir",
                    "rmdir",
                    "find",
                    "grep",
                    "rg",
                    "ack",
                    "vim",
                    "vi",
                    "nano",
                    "emacs",
                    "code",
                    "sublime",
                    "subl",
                    "file",
                    "stat",
                    "wc",
                    "du",
                    "df",
                }

                self.pattern_commands = {"grep", "rg", "ack", "sed", "awk", "locate"}
                self.path_cache = {}
                self.cache_size = 100

            def _get_path_style(self, command, target_arg):
                from ..config import Config

                if not Config.PATH_HIGHLIGHT.get("enabled", True):
                    return None

                require_existing = {
                    "cd",
                    "cat",
                    "head",
                    "tail",
                    "less",
                    "more",
                    "bat",
                    "batcat",
                    "ls",
                    "rm",
                    "mv",
                    "cp",
                    "ln",
                    "chmod",
                    "file",
                    "stat",
                    "vim",
                    "vi",
                    "nano",
                    "emacs",
                    "code",
                    "sublime",
                    "subl",
                    "wc",
                    "du",
                    "df",
                    "find",
                }

                create_new = {"touch", "mkdir"}

                if command in create_new:
                    return Config.PATH_HIGHLIGHT.get("create_style", "underline cyan")

                exists = self._check_path_exists(target_arg, command)

                if command in require_existing:
                    if exists:
                        return Config.PATH_HIGHLIGHT.get(
                            "valid_style", "underline cyan"
                        )
                    else:
                        return Config.PATH_HIGHLIGHT.get(
                            "invalid_style", "underline red"
                        )

                return Config.PATH_HIGHLIGHT.get("valid_style", "underline cyan")

            def _check_path_exists(self, path, command=None):
                cache_key = (path, command)
                if cache_key in self.path_cache:
                    return self.path_cache[cache_key]

                if path in {".", ".."}:
                    self.path_cache[cache_key] = True
                    return True

                if (
                    not "/" in path
                    and not "." in path
                    and not path.startswith("~")
                    and not os.path.isabs(path)
                    and len(path) > 1
                ):
                    self.path_cache[cache_key] = True
                    return True

                try:
                    cwd = os.getcwd()
                    if hasattr(self.shell, "command_executor"):
                        executor = self.shell.command_executor
                        if hasattr(executor, "cwd"):
                            cwd = executor.cwd
                        elif hasattr(executor, "get_cwd"):
                            cwd = executor.get_cwd()

                    check_path = path
                    if check_path.startswith("~"):
                        check_path = os.path.expanduser(check_path)
                    elif not os.path.isabs(check_path):
                        check_path = os.path.join(cwd, check_path)

                    if command == "cd":
                        exists = os.path.isdir(check_path)
                    else:
                        exists = os.path.exists(check_path)

                    if len(self.path_cache) >= self.cache_size:
                        self.path_cache.pop(next(iter(self.path_cache)))
                    self.path_cache[cache_key] = exists

                    return exists
                except Exception:
                    return False

            def apply_transformation(self, transformation_input):
                document = transformation_input.document
                text = document.text.strip()

                if not text:
                    return Transformation(transformation_input.fragments)

                parts = text.split()
                if not parts:
                    return Transformation(transformation_input.fragments)

                command = parts[0]
                if command not in self.file_commands:
                    return Transformation(transformation_input.fragments)

                path_args = []  # List of (arg, index) tuples

                commands_all_args_are_paths = {
                    "ls",
                    "cd",
                    "mkdir",
                    "rm",
                    "cp",
                    "mv",
                    "touch",
                    "rmdir",
                }

                is_pattern_command = command in self.pattern_commands
                pattern_found = False

                i = 1
                while i < len(parts):
                    arg = parts[i]

                    if arg.startswith("-"):
                        i += 1
                        continue

                    if arg in {"|", "&&", "||", ";", ">", "<", ">>", "2>", "&>"}:
                        break

                    if i > 1 and parts[i - 1] in {">", "<", ">>", "2>", "&>"}:
                        i += 1
                        continue

                    if is_pattern_command and not pattern_found:
                        pattern_found = True
                        i += 1
                        continue

                    if arg.isdigit():
                        i += 1
                        continue

                    try:
                        float(arg)
                        i += 1
                        continue
                    except ValueError:
                        pass

                    if command in commands_all_args_are_paths:
                        path_args.append((arg, i))
                    else:
                        is_likely_path = (
                            "/" in arg
                            or "." in arg
                            or arg.endswith("/")
                            or len(arg)
                            > 2  # Avoid highlighting short strings like "a", "b"
                        )

                        if is_likely_path:
                            path_args.append((arg, i))

                    i += 1

                if not path_args:
                    return Transformation(transformation_input.fragments)

                full_text = "".join(
                    fragment_text for _, fragment_text in transformation_input.fragments
                )

                cmd_pos = full_text.lower().find(command.lower())
                if cmd_pos == -1:
                    return Transformation(transformation_input.fragments)

                highlights = []

                search_start = cmd_pos + len(command)

                for target_arg, arg_index in path_args:
                    position = full_text.lower().find(target_arg.lower(), search_start)
                    if position == -1:
                        position = full_text.find(target_arg, search_start)
                        if position == -1:
                            continue  # Skip this argument if not found

                    path_style = self._get_path_style(command, target_arg)
                    if path_style is None:
                        continue  # Skip if highlighting disabled for this path

                    highlights.append(
                        {
                            "start": position,
                            "end": position + len(target_arg),
                            "style": path_style,
                        }
                    )

                    search_start = position + len(target_arg)

                if not highlights:
                    return Transformation(transformation_input.fragments)

                highlights.sort(key=lambda x: x["start"])

                original_fragments = transformation_input.fragments
                new_fragments = []

                current_global_pos = 0

                for fragment_style, fragment_text in original_fragments:
                    if (
                        "suggestion" in fragment_style
                        or "auto" in fragment_style
                        or "completion" in fragment_style
                    ):
                        new_fragments.append((fragment_style, fragment_text))
                        current_global_pos += len(fragment_text)
                    else:
                        fragment_len = len(fragment_text)
                        fragment_start = current_global_pos
                        fragment_end = current_global_pos + fragment_len

                        fragment_highlights = []
                        for hl in highlights:
                            hl_start = hl["start"]
                            hl_end = hl["end"]
                            if hl_start < fragment_end and hl_end > fragment_start:
                                overlap_start = max(hl_start, fragment_start)
                                overlap_end = min(hl_end, fragment_end)
                                fragment_highlights.append(
                                    {
                                        "start": overlap_start,
                                        "end": overlap_end,
                                        "style": hl["style"],
                                    }
                                )

                        if fragment_highlights:
                            fragment_highlights.sort(key=lambda x: x["start"])

                            current_local_pos = 0  # Position within fragment

                            for hl in fragment_highlights:
                                hl_local_start = hl["start"] - fragment_start
                                hl_local_end = hl["end"] - fragment_start

                                if hl_local_start > current_local_pos:
                                    before = fragment_text[
                                        current_local_pos:hl_local_start
                                    ]
                                    new_fragments.append((fragment_style, before))

                                if hl_local_end > hl_local_start:
                                    highlight_text = fragment_text[
                                        hl_local_start:hl_local_end
                                    ]
                                    new_fragments.append((hl["style"], highlight_text))

                                current_local_pos = hl_local_end

                            if current_local_pos < fragment_len:
                                after = fragment_text[current_local_pos:]
                                new_fragments.append((fragment_style, after))
                        else:
                            new_fragments.append((fragment_style, fragment_text))

                        current_global_pos += fragment_len

                return Transformation(new_fragments)

        return PathHighlightProcessor(self)

    def _setup_keybindings(self) -> None:
        self.bindings = KeyBindings()

        @self.bindings.add("c-s")
        def switch_to_shell(event):
            self.mode = "shell"
            self.ui.show_mode_switch("Shell Mode")

        @self.bindings.add("escape", "h")
        def show_help(event):
            self.ui.show_help()

        @self.bindings.add("escape", "c")
        def clear_context(event):
            self.ui.show_context_cleared()

        @self.bindings.add("escape", "r")
        def refresh_completion(event):
            self.completion_manager.clear_cache()

        @self.bindings.add("c-z")
        def suspend_foreground_job(event):
            if hasattr(self.command_executor, "_suspend_foreground_job"):
                if self.command_executor._suspend_foreground_job():
                    event.app.exit(result=False)
                else:
                    pass

        @self.bindings.add("c-c")
        def interrupt_or_exit(event):
            if (
                hasattr(self.command_executor, "_interrupt_foreground_job")
                and self.command_executor._interrupt_foreground_job()
            ):
                event.app.exit(result=False)
            else:
                pass

    def execute_shell_command(self, command: str) -> Optional[str]:
        return self.command_executor.execute(command)

    def _handle_config_command(self, command: str) -> bool:
        parts = command.split()
        action = parts[1].lower() if len(parts) > 1 else ""

        if action == "reload":
            self._reload_configuration()
            return True

        usage = "config reload"
        self.console.print(
            PanelTheme.build(
                f"[yellow]Unknown config command.[/yellow]\nUsage: [cyan]{usage}[/cyan]",
                title="Config",
                style="warning",
                fit=True,
            )
        )
        return True

    def handle_shell_special_commands(self, user_input: str) -> bool:
        normalized = user_input.strip()

        if normalized in {"/config_reload", "config_reload"}:
            return self._handle_config_command("config reload")

        if normalized.startswith("config"):
            return self._handle_config_command(normalized)

        return False

    def _reload_configuration(self) -> None:
        with self.ui.create_status("Reloading configuration..."):
            success = Config.reload()

        if not success:
            self.console.print(
                PanelTheme.build(
                    "[red]Failed to reload configuration. Check config.ini for errors.[/red]",
                    title="Config",
                    style="error",
                    fit=True,
                )
            )
            return

        self.session = PromptSession(history=DirectoryIsolatedHistory())
        self.completion_manager = create_completion_manager()
        self.command_executor.set_completion_manager(self.completion_manager)
        self.command_executor.refresh_configuration()
        self.prompt_lexer = self._create_prompt_lexer()

        self.console.print(
            PanelTheme.build(
                f"[green]Configuration reloaded from[/green] [cyan]{Config.CONFIG_FILE}[/cyan]",
                title="Config",
                style="success",
                fit=True,
            )
        )

    def _get_dynamic_prompt(self) -> str:
        if self.command_executor.script_runtime.awaiting_more_input:
            return " ░░░ "
        if self._shell_awaiting_more:
            return " ░░░ "
        return self.ui.get_prompt_text(self.mode)

    def _get_prompt_default_text(self) -> str:
        if self.command_executor.script_runtime.awaiting_more_input:
            indent = self.command_executor.script_runtime.continuation_indent
            return indent if indent else "    "
        if self._shell_awaiting_more:
            return "    "
        return ""

    def _handle_continuation_command(self, user_input: str) -> bool:
        normalized = user_input.strip().lower()
        if normalized == "cancel":
            self.command_executor.script_runtime.cancel_pending_block()
            return True
        return False

    def _handle_script_submission(self, user_input: str) -> None:
        normalized = user_input.strip()
        if normalized and self.command_executor._handle_script_active_shortcuts(
            normalized
        ):
            return
        if self._handle_continuation_command(user_input):
            return
        if not normalized:
            self.command_executor.script_runtime.run_line("")
            return

        lines = user_input.replace("\r\n", "\n").split("\n")
        adjusted = []
        for index, line in enumerate(lines):
            if index > 0 and adjusted:
                prev = adjusted[-1]
                if (
                    prev.rstrip().endswith(":")
                    and line
                    and not line.startswith(" ")
                    and not line.startswith("\t")
                ):
                    line = "    " + line
            adjusted.append(line)

        for line in adjusted:
            self.command_executor.script_runtime.run_line(line)

    def _are_delimiters_balanced(self, text: str) -> bool:
        stack = []
        in_single_quote = False
        in_double_quote = False
        in_backtick = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == "'" and not in_double_quote and not in_backtick:
                in_single_quote = not in_single_quote
                continue
            if char == '"' and not in_single_quote and not in_backtick:
                in_double_quote = not in_double_quote
                continue
            if char == "`" and not in_single_quote and not in_double_quote:
                in_backtick = not in_backtick
                continue

            if in_single_quote or in_double_quote or in_backtick:
                continue

            if char in "{[(":
                stack.append(char)
            elif char in "}])":
                if not stack:
                    return False
                opening = stack.pop()
                if (
                    (opening == "{" and char != "}")
                    or (opening == "[" and char != "]")
                    or (opening == "(" and char != ")")
                ):
                    return False

        if in_single_quote or in_double_quote or in_backtick:
            return False

        return len(stack) == 0

    def _get_current_shell(self) -> str:
        from ..config import Config

        shell_path = Config.get_shell()
        shell_name = os.path.basename(shell_path).lower()

        if "bash" in shell_name:
            return "bash"
        elif "zsh" in shell_name:
            return "zsh"
        elif "fish" in shell_name:
            return "fish"
        elif "nu" in shell_name:
            return "nushell"
        elif "xonsh" in shell_name:
            return "xonsh"
        else:
            return "bash"

    def _shell_starts_block(self, stripped: str) -> bool:
        if self._are_delimiters_balanced(stripped):
            shell_type = self._get_current_shell()

            if shell_type in ["bash", "zsh"]:
                if (
                    stripped.endswith("do")
                    or stripped.endswith("then")
                    or stripped.endswith("in")
                ):
                    return True
                if stripped.endswith("\\"):
                    return True
                if stripped.startswith("|"):
                    return True
            elif shell_type == "fish":
                if stripped.startswith("function ") and not stripped.endswith("end"):
                    return True
                if stripped.startswith("if ") and not stripped.endswith("end"):
                    return True
                if stripped.startswith("begin") and not stripped.endswith("end"):
                    return True

            elif shell_type == "nushell":
                count_open = stripped.count("{")
                count_close = stripped.count("}")
                if count_open > count_close:
                    return True

            elif shell_type == "xonsh":
                if stripped.endswith(":"):
                    return True

            return False

        return (
            stripped.endswith("do")
            or stripped.endswith("then")
            or stripped.endswith("in")
            or stripped.endswith("{")
            or stripped.endswith("\\")
            or stripped.startswith("|")
        )

    def _shell_ends_block(self, stripped: str) -> bool:
        shell_type = self._get_current_shell()

        if shell_type in ["bash", "zsh"]:
            if (
                stripped == "fi"
                or stripped == "done"
                or stripped == "esac"
                or stripped == "}"
                or stripped.endswith("; fi")
                or stripped.endswith("; done")
                or stripped.endswith("; esac")
            ):
                return True

        elif shell_type == "fish":
            if stripped == "end" or stripped.endswith("; end"):
                return True

        elif shell_type == "nushell":
            if stripped == "}" or stripped.endswith("; }"):
                return True

        elif shell_type == "xonsh":
            if not stripped:
                return True
            if self._shell_buffer:
                first_line = self._shell_buffer[0]
                first_indent = len(first_line) - len(first_line.lstrip())
                current_indent = len(stripped) - len(stripped.lstrip())
                if current_indent < first_indent:
                    return True

        if self._shell_buffer:
            if any(line.rstrip().endswith("\\") for line in self._shell_buffer):
                if not stripped.endswith("\\") and stripped != "":
                    return True

        if self._shell_buffer:
            all_lines = "\n".join(self._shell_buffer + [stripped])
            if self._are_delimiters_balanced(all_lines):
                first_line = self._shell_buffer[0].strip()
                needs_explicit_end = False

                if shell_type in ["bash", "zsh"]:
                    if first_line.startswith("for ") or "; do" in first_line:
                        needs_explicit_end = True
                    elif first_line.startswith("if ") or "; then" in first_line:
                        needs_explicit_end = True
                    elif first_line.startswith("while ") or first_line.startswith(
                        "until "
                    ):
                        needs_explicit_end = True
                    elif first_line.startswith("case "):
                        needs_explicit_end = True

                if not needs_explicit_end:
                    return True

        return False

    def _shell_begin(self, line: str) -> None:
        self._shell_awaiting_more = True
        self._shell_buffer = [line]

    def _shell_append(self, line: str) -> None:
        self._shell_buffer.append(line)

    def _shell_flush_execute(self) -> Optional[str]:
        combined = "\n".join(self._shell_buffer)
        self._shell_buffer.clear()
        self._shell_awaiting_more = False
        return self.command_executor.execute(combined)

    def run(self) -> None:
        self.ui.show_welcome()

        session_history = DirectoryFilteredAutoSuggest(self.session.history, self)

        try:
            while True:
                try:
                    current_completer = None
                    if self.mode == "shell":
                        current_completer = self.completion_manager.get_completer()

                    script_active = self.command_executor.script_runtime.is_active
                    default_text = self._get_prompt_default_text()
                    prompt_kwargs = {
                        "message": self._get_dynamic_prompt,
                        "key_bindings": self.bindings,
                        "style": self.ui.get_style(),
                        "auto_suggest": session_history,
                        "clipboard": PyperclipClipboard(),
                        "completer": current_completer,
                        "lexer": self.prompt_lexer,
                        "color_depth": ColorDepth.TRUE_COLOR,
                        "complete_while_typing": Config.COMPLETION_AUTO_POPUP,
                        "default": default_text,
                        "cursor": CursorShape.BEAM,
                        "enable_suspend": True,
                        "refresh_interval": 0.5
                        if Config.UI_REFRESH_INTERVAL_ENABLED
                        else None,
                    }

                    if Config.PROMPT_PLACEHOLDER:
                        prompt_kwargs["placeholder"] = HTML(Config.PROMPT_PLACEHOLDER)

                    if (
                        hasattr(self, "command_highlight_processor")
                        and Config.COMMAND_HIGHLIGHT
                    ):
                        default_processors = prompt_kwargs.get("input_processors", [])
                        if default_processors is None:
                            default_processors = []
                        prompt_kwargs["input_processors"] = default_processors + [
                            self.command_highlight_processor
                        ]

                    if hasattr(self, "path_highlight_processor"):
                        default_processors = prompt_kwargs.get("input_processors", [])
                        if default_processors is None:
                            default_processors = []
                        prompt_kwargs["input_processors"] = default_processors + [
                            self.path_highlight_processor
                        ]

                    user_input = self.session.prompt(**prompt_kwargs)

                    if self.command_executor.script_runtime.is_active:
                        if self.command_executor.script_runtime.awaiting_more_input:
                            if not user_input.strip():
                                self.command_executor.script_runtime.run_line("")
                                continue
                            if self._handle_continuation_command(user_input):
                                continue
                            indent = (
                                self.command_executor.script_runtime.continuation_indent
                                or "    "
                            )
                            continued_line = f"{indent}{user_input.lstrip()}"
                            self.command_executor.script_runtime.run_line(
                                continued_line
                            )
                            continue
                        self._handle_script_submission(user_input)
                        continue
                    else:
                        stripped = user_input.strip()
                        if self._shell_awaiting_more:
                            self._shell_append(user_input)
                            if self._shell_ends_block(stripped):
                                result = self._shell_flush_execute()
                                if result == "exit":
                                    return
                            continue
                        else:
                            if self._shell_starts_block(stripped):
                                self._shell_begin(user_input)
                                continue
                            user_input = user_input.strip()
                            if not user_input:
                                continue

                            if self.handle_shell_special_commands(user_input):
                                continue

                            result = self.execute_shell_command(user_input)
                            if result == "exit":
                                break

                except EOFError:
                    if self.command_executor.in_script_mode():
                        self.command_executor.exit_script_mode()
                        continue

                    self.ui.display_goodbye()
                    break

                except KeyboardInterrupt:
                    self.ui.display_goodbye()
                    break

        except KeyboardInterrupt:
            self.ui.display_goodbye()
        finally:
            if hasattr(self.command_executor, "_cleanup_all_jobs"):
                self.command_executor._cleanup_all_jobs()

    def _create_prompt_lexer(self):
        choice = Config.get_prompt_lexer_choice().strip()
        if not choice or choice.lower() == "auto":
            return None

        if not find_lexer_class_by_name:
            return None

        lexer_cls = find_lexer_class_by_name(choice)
        if lexer_cls is None:
            return None

        return PygmentsLexer(lexer_cls)
