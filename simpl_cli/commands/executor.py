#!/usr/bin/env python3
import collections
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import signal
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from rich.columns import Columns
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..environment import env_detector
from ..core.script_runtime import ScriptRuntime
from ..ui.theme import PanelTheme


class ShellCommandExecutor:
    def __init__(
        self,
        console: Console,
        ui,
        streaming_ui,
        context_manager,
        completion_manager,
    ) -> None:
        self.console = console
        self.ui = ui
        self.streaming_ui = streaming_ui
        self.context_manager = context_manager
        self.completion_manager = completion_manager
        self.previous_directory = os.getcwd()
        self.aliases = self._load_aliases()
        self._available_commands_cache: Optional[set[str]] = None
        self.script_runtime = ScriptRuntime(console)

        self.jobs: Dict[int, Dict[str, Any]] = {}
        self.task_queue = collections.deque()
        self.next_job_id = 1
        self.foreground_job: Optional[int] = None

    def in_script_mode(self) -> bool:
        return self.script_runtime.is_active or self.script_runtime.awaiting_more_input

    def exit_script_mode(self, announce: bool = True) -> None:
        self.script_runtime.deactivate(announce=announce)

    def set_completion_manager(self, completion_manager) -> None:
        self.completion_manager = completion_manager

    def refresh_configuration(self) -> None:
        self.aliases = self._load_aliases()
        self._available_commands_cache = None

    def execute(self, command: str) -> Optional[str]:
        if not command.strip():
            return None

        try:
            normalized = command.strip()

            if normalized == "/help":
                self.ui.show_help()
                return None

            if normalized in {"/config_reload", "config_reload"}:
                self._handle_config_reload_command()
                return None

            if normalized == "/cleanup_memory":
                self._handle_cleanup_memory_command()
                return None

            if self._handle_environment_commands(command):
                return None

            if self._handle_script_commands(normalized):
                return None

            if self.script_runtime.is_active:
                special_handled = self._handle_script_active_shortcuts(normalized)
                if special_handled:
                    return None
                self.script_runtime.run_line(command)
                return None

            if self._handle_alias_management(normalized):
                return None

            if self._handle_export_command(normalized):
                return None

            if self._handle_unset_command(normalized):
                return None

            if self._handle_assignment_only(normalized):
                return None

            command = self._expand_alias(command)
            normalized = command.strip()

            if normalized.startswith("files"):
                self._handle_files_command(command)
                return None

            if (
                normalized in {"jobs", "fg", "bg"}
                or normalized.startswith("fg ")
                or normalized.startswith("bg ")
            ):
                self._handle_job_control_command(normalized)
                return None

            if normalized == "exit":
                return "exit"
            if normalized == "clear":
                self._true_clear_terminal()
                return None
            if normalized == "cd" or normalized.startswith("cd "):
                if self._has_shell_operator(command):
                    self._handle_regular_command(command)
                    return None

                self._handle_cd_command(normalized)
                self.completion_manager.update_cache()
                return None
            if normalized.startswith("source "):
                self._handle_source_command(normalized)
                return None
            if normalized == "deactivate":
                self._handle_deactivate_command(normalized)
                return None
            if (
                normalized.endswith("/activate")
                or normalized.endswith("\\activate")
                or normalized.startswith("activate ")
            ):
                self._handle_activate_command(normalized)
                return None

            if self._is_interactive_command(command):
                self._handle_interactive_command(command)
                return None

            if self._handle_auto_cd(normalized):
                return None

            self._handle_regular_command(command)
        except KeyboardInterrupt:
            self.ui.display_interrupt()
        except Exception as error:
            self.ui.display_error(command, f"Error: {error}")
            self.context_manager.add_shell_context(command, f"Error: {error}")

        return None

    def _handle_script_commands(self, command: str) -> bool:
        if command in {"py", "py enter"}:
            self.script_runtime.activate()
            return True

        if command in {"py exit", "exitpy"}:
            self.script_runtime.deactivate()
            return True

        if command == "py reset":
            self.script_runtime.reset()
            return True

        if command == "py cancel":
            self.script_runtime.cancel_pending_block()
            return True

        if command.startswith("py "):
            code_line = command[3:].lstrip()
            if code_line:
                self.script_runtime.run_inline(code_line)
            else:
                self.script_runtime.activate()
            return True

        return False

    def _handle_script_active_shortcuts(self, command: str) -> bool:
        if command in {"exit", "exit()", "quit", "quit()"}:
            self.script_runtime.deactivate()
            return True

        if command == "clear":
            self.script_runtime.deactivate(announce=False)
            self._true_clear_terminal()
            return True

        if command == "cancel":
            self.script_runtime.cancel_pending_block()
            return True

        return False

    def _true_clear_terminal(self) -> None:
        clear_sequence = "\033[2J\033[H"
        sys.stdout.write(clear_sequence)
        sys.stdout.flush()

        try:
            if os.name == "posix":
                os.system("clear")
            elif os.name == "nt":
                os.system("cls")
        except Exception:
            self.console.clear()

    def _is_interactive_command(self, command: str) -> bool:
        if self._is_local_executable_invocation(command):
            return True

        if self._has_background_execution(command):
            return True

        if self._is_recursive_ls(command):
            return True

        base_cmd = command.strip().split()[0]
        base_cmd = os.path.basename(base_cmd)

        if base_cmd in {"jobs", "fg", "bg"}:
            return True

        if base_cmd in Config.INTERACTIVE_COMMANDS:
            return True

        if "|" in command:
            parts = command.split("|")
            for part in parts:
                if part.strip().split()[0] in Config.INTERACTIVE_COMMANDS:
                    return True

        return False

    def _is_recursive_ls(self, command: str) -> bool:
        try:
            tokens = shlex.split(command)
        except ValueError:
            return False

        idx = 0
        while idx < len(tokens) and self._looks_like_env_assignment(tokens[idx]):
            idx += 1

        if idx >= len(tokens):
            return False

        cmd_token = tokens[idx]
        cmd_base = os.path.basename(cmd_token)

        if cmd_base == "sudo" and idx + 1 < len(tokens):
            idx += 1
            cmd_token = tokens[idx]
            cmd_base = os.path.basename(cmd_token)

        if cmd_base != "ls":
            return False

        for token in tokens[idx + 1 :]:
            if token == "--":
                continue
            if token.startswith("-") and "R" in token:
                return True

        return False

    def _has_background_execution(self, command: str) -> bool:
        stripped = command.rstrip()
        if not stripped:
            return False

        i = len(stripped) - 1

        if i < 0:
            return False

        if stripped[i] != "&":
            return False

        if i > 0 and stripped[i - 1] == "&":
            return False

        return True

    def _is_local_executable_invocation(self, command: str) -> bool:
        if not command.strip() or self._has_shell_operator(command):
            return False

        executable_path = self._resolve_local_executable(command)
        return executable_path is not None

    def _resolve_local_executable(self, command: str) -> Optional[str]:
        try:
            tokens = shlex.split(command)
        except ValueError:
            return None

        if not tokens:
            return None

        candidate = None
        for token in tokens:
            if self._looks_like_env_assignment(token):
                continue
            candidate = token
            break

        if not candidate:
            return None

        if not self._looks_like_path(candidate):
            return None

        expanded = os.path.expanduser(candidate)
        if not os.path.isabs(expanded):
            expanded = os.path.abspath(expanded)

        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
        return None

    @staticmethod
    def _looks_like_env_assignment(token: str) -> bool:
        return (
            "=" in token
            and not token.startswith("./")
            and not token.startswith("../")
            and not token.startswith("/")
            and os.sep not in token
        )

    @staticmethod
    def _looks_like_path(token: str) -> bool:
        if not token:
            return False
        if token.startswith(("./", "../", "/", "~")):
            return True
        if os.sep in token:
            return True
        if os.path.altsep and os.path.altsep in token:
            return True
        return False

    @staticmethod
    def _has_shell_operator(command: str) -> bool:
        operators = ["|", "&&", "||", ";", ">", "<"]
        return any(op in command for op in operators)

    def _handle_environment_commands(self, command: str) -> bool:
        if not command.startswith("!"):
            return False

        env_cmd = command[1:]

        try:
            handlers = {
                "env": self._show_environment_status,
                "status": self._show_detailed_system_info,
                "git": self._show_git_info,
                "python": self._show_python_info,
            }

            if env_cmd in handlers:
                handlers[env_cmd]()
                self.context_manager.add_shell_context(
                    command, f"Environment command '{env_cmd}' executed"
                )
                return True

            error_msg = f"Unknown environment command: {env_cmd}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, f"Error: {error_msg}")
            return True
        except Exception as error:
            error_msg = f"Environment command error: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, f"Error: {error_msg}")
            return True

    def _show_environment_status(self) -> None:
        env_info = env_detector.get_all_environments()

        table = Table(
            title="Environment Status",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Type", style="cyan", width=12)
        table.add_column("Status", style="green", width=20)
        table.add_column("Details", style="yellow")

        if env_info["python"]:
            py_env = env_info["python"]
            table.add_row(
                "Python",
                py_env["name"],
                f"v{py_env['python_version']} ({py_env['type']})",
            )
        else:
            table.add_row(
                "Python",
                "System",
                f"v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            )

        if env_info["git"]:
            git_info = env_info["git"]
            status_indicator = "" if git_info.get("has_changes") else ""
            table.add_row(
                "Git",
                f"{status_indicator} {git_info['branch']}",
                f"Ahead: {git_info.get('ahead', 0)}, Behind: {git_info.get('behind', 0)}",
            )
        else:
            table.add_row("Git", "Not a repository", "-")

        if env_info["node"]:
            node_info = env_info["node"]
            modules_status = "" if node_info["has_modules"] else ""
            table.add_row(
                "Node.js",
                node_info["name"],
                f"v{node_info['version']} (modules: {modules_status})",
            )
        else:
            table.add_row("Node.js", "Not detected", "-")

        if env_info["docker"]:
            docker_info = env_info["docker"]
            docker_details: list[str] = []
            if docker_info.get("has_dockerfile"):
                docker_details.append("Dockerfile")
            if docker_info.get("has_compose"):
                docker_details.append("Compose")
            if docker_info.get("inside_container"):
                docker_details.append("In Container")

            table.add_row(
                "Docker",
                "Available",
                ", ".join(docker_details) if docker_details else "Basic",
            )
        else:
            table.add_row("Docker", "Not detected", "-")

        self.console.print(table)

    def _show_detailed_system_info(self) -> None:
        system_info = env_detector.get_system_info()
        env_info = env_detector.get_all_environments()

        system_text = (
            f"[bold cyan]System Resources[/bold cyan]\n"
            f"CPU Usage: {system_info['cpu_percent']:.1f}%\n"
            f"Memory Usage: {system_info['memory_percent']:.1f}%\n"
            f"Available Memory: {system_info['memory_available']}MB\n"
            f"Load Average: {system_info['load_average']:.2f}\n"
            f"Uptime: {system_info['uptime']}"
        )

        env_summary = "[bold green]Active Environments[/bold green]\n"
        active_envs: list[str] = []

        if env_info["python"]:
            active_envs.append(f"󰌠 {env_info['python']['display']}")
        if env_info["git"]:
            git_status = "" if env_info["git"].get("has_changes") else ""
            active_envs.append(f"{git_status} {env_info['git']['display']}")
        if env_info["node"]:
            active_envs.append(f"󰎙 {env_info['node']['display']}")
        if env_info["docker"]:
            active_envs.append(f"󰡨 {env_info['docker']['display']}")

        if active_envs:
            env_summary += "\n".join(active_envs)
        else:
            env_summary += "No special environments detected"

        cwd = os.getcwd()
        dir_info = f"[bold yellow]Current Directory[/bold yellow]\n{cwd}"

        panels = [
            PanelTheme.build(system_text, title="System", style="info"),
            PanelTheme.build(env_summary, title="Environments", style="info"),
            PanelTheme.build(dir_info, title="Location", style="info"),
        ]

        self.console.print(Columns(panels))

    def _show_git_info(self) -> None:
        git_info = env_detector.get_git_status()

        if not git_info:
            self.console.print("[red]Not in a Git repository[/red]")
            return

        table = Table(title="Git Repository Information", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Branch", git_info["branch"])
        table.add_row(
            "Status",
            "[red][/red] Modified"
            if git_info.get("has_changes")
            else "[green][/green] Clean",
        )
        table.add_row("Commits Ahead", str(git_info.get("ahead", 0)))
        table.add_row("Commits Behind", str(git_info.get("behind", 0)))

        self.console.print(table)

        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and result.stdout:
                commits = result.stdout.strip()
                self.console.print(
                    PanelTheme.build(commits, title="Recent Commits", style="info")
                )
        except Exception:
            pass

    def _show_python_info(self) -> None:
        py_env = env_detector.get_python_environment()

        table = Table(title="Python Environment", show_header=True)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row(
            "Python Version",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        table.add_row("Python Executable", sys.executable)

        if py_env:
            table.add_row("Virtual Environment", py_env["name"])
            table.add_row("Environment Type", py_env["type"])
            if "path" in py_env:
                table.add_row("Environment Path", py_env["path"])
        else:
            table.add_row("Virtual Environment", "None (System Python)")

        python_paths = sys.path[:3]
        if len(sys.path) > 3:
            python_paths.append("...")
        table.add_row("Python Path", "\n".join(python_paths))

        self.console.print(table)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[2:]
                if lines:
                    packages = "\n".join(lines[:10])
                    if len(lines) > 10:
                        packages += f"\n... and {len(lines) - 10} more packages"
                    self.console.print(
                        PanelTheme.build(
                            packages, title="Installed Packages (Top 10)", style="info"
                        )
                    )
        except Exception:
            pass

    def _handle_auto_cd(self, command: str) -> bool:
        cmd = command.strip()

        if " " in cmd:
            return False

        if not cmd:
            return False

        if cmd in {".", "..", "-"}:
            self._handle_cd_command(f"cd {cmd}")
            return True

        if self._is_known_command(cmd):
            return False

        path = cmd
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)

        if os.path.isdir(path):
            self._handle_cd_command(f"cd {cmd}")
            return True

        if cmd.startswith("~"):
            expanded = os.path.expanduser(cmd)
            if os.path.isdir(expanded):
                self._handle_cd_command(f"cd {cmd}")
                return True

        return False

    def _is_known_command(self, cmd: str) -> bool:

        builtins = {
            "cd",
            "ls",
            "pwd",
            "echo",
            "cat",
            "mkdir",
            "rm",
            "cp",
            "mv",
            "grep",
            "find",
            "chmod",
            "chown",
            "ps",
            "kill",
            "jobs",
            "fg",
            "bg",
            "export",
            "unset",
            "alias",
            "unalias",
            "source",
            ".",
            "exit",
            "clear",
            "history",
            "type",
            "which",
            "whereis",
        }

        if cmd in builtins:
            return True

        if cmd in self.aliases:
            return True

        path_env = os.environ.get("PATH", "")
        for directory in path_env.split(os.pathsep):
            if not directory:
                continue
            executable_path = os.path.join(directory, cmd)
            if os.path.isfile(executable_path) and os.access(executable_path, os.X_OK):
                return True

        return False

    def _handle_cd_command(self, command: str) -> None:
        path = command[3:].strip()
        if not path:
            path = os.path.expanduser("~")
        elif path == "-":
            path = self.previous_directory or os.path.expanduser("~")
        else:
            path = os.path.expanduser(path)

        try:
            old_dir = os.getcwd()
            os.chdir(path)
            new_dir = os.getcwd()
            self.previous_directory = old_dir
            if Config.CD_FEEDBACK_ENABLED:
                self.ui.display_directory_change(command, new_dir)
            self.context_manager.add_shell_context(
                command, f"Changed directory to: {new_dir}"
            )
        except OSError as error:
            error_msg = f"cd: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)

    def _handle_source_command(self, command: str) -> None:
        source_file = command[7:].strip()

        if not source_file:
            error_msg = "source: missing file operand"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)
            return

        source_file = os.path.expanduser(source_file)

        if not os.path.exists(source_file):
            error_msg = f"source: {source_file}: No such file or directory"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)
            return

        bash_command = f'source "{source_file}" && env'
        self._execute_source_like_command(command, bash_command)

    def _handle_deactivate_command(self, command: str) -> None:
        try:
            virtual_env = os.environ.get("VIRTUAL_ENV")
            conda_env = os.environ.get("CONDA_DEFAULT_ENV")

            if not virtual_env and not conda_env:
                error_msg = "deactivate: No virtual environment currently activated"
                self.ui.display_error(command, error_msg)
                self.context_manager.add_shell_context(command, error_msg)
                return

            env_name = ""
            env_type = ""

            if virtual_env:
                env_name = os.path.basename(virtual_env)
                env_type = "virtualenv/venv"
            elif conda_env and conda_env != "base":
                env_name = conda_env
                env_type = "conda"

            with self.ui.create_status("Deactivating virtual environment..."):
                if virtual_env:
                    current_path = os.environ.get("PATH", "")
                    venv_bin = os.path.join(virtual_env, "bin")
                    path_parts = current_path.split(os.pathsep)
                    new_path_parts = [
                        part for part in path_parts if not part.startswith(venv_bin)
                    ]
                    os.environ["PATH"] = os.pathsep.join(new_path_parts)

                    env_vars_to_remove = ["VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT"]
                    removed_vars = []

                    for var in env_vars_to_remove:
                        if var in os.environ:
                            del os.environ[var]
                            removed_vars.append(var)

                    original_ps1 = os.environ.get("_OLD_VIRTUAL_PS1")
                    if original_ps1:
                        os.environ["PS1"] = original_ps1
                        del os.environ["_OLD_VIRTUAL_PS1"]
                        removed_vars.append("_OLD_VIRTUAL_PS1")

                elif conda_env:
                    conda_vars_to_remove = [
                        "CONDA_DEFAULT_ENV",
                        "CONDA_PREFIX",
                        "CONDA_PYTHON_EXE",
                    ]
                    removed_vars = []

                    for var in conda_vars_to_remove:
                        if var in os.environ:
                            del os.environ[var]
                            removed_vars.append(var)

                    conda_base = os.environ.get("CONDA_EXE")
                    if conda_base:
                        conda_base_bin = os.path.dirname(conda_base)
                        current_path = os.environ.get("PATH", "")

                        if conda_base_bin not in current_path:
                            os.environ["PATH"] = (
                                f"{conda_base_bin}{os.pathsep}{current_path}"
                            )

            success_msg = f" Deactivated {env_type} environment: {env_name}"
            self.console.print(f"[green]{success_msg}[/green]")
            self.context_manager.add_shell_context(command, success_msg)

            if "removed_vars" in locals() and removed_vars:
                self.console.print(
                    f"[dim]Removed environment variables: {', '.join(removed_vars)}[/dim]"
                )

            current_path = os.environ.get("PATH", "")
            path_parts = current_path.split(os.pathsep)[:3]
            self.console.print(
                f"[dim]Updated PATH: {os.pathsep.join(path_parts)}...[/dim]"
            )

        except Exception as error:
            error_msg = f"deactivate: Error deactivating environment: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)

    def _handle_activate_command(self, command: str) -> None:
        try:
            activate_path = ""

            if command.endswith("/activate") or command.endswith("\\activate"):
                activate_path = command
            elif command.startswith("activate "):
                env_name = command[9:].strip()
                conda_exe = os.environ.get("CONDA_EXE")
                if conda_exe:
                    bash_command = (
                        f'source "{os.path.dirname(conda_exe)}/activate" '
                        f"&& conda activate {env_name} && env"
                    )
                    self._execute_source_like_command(command, bash_command)
                    return

                error_msg = f"activate: conda not found, cannot activate environment '{env_name}'"
                self.ui.display_error(command, error_msg)
                self.context_manager.add_shell_context(command, error_msg)
                return

            if activate_path:
                activate_path = os.path.expanduser(activate_path)

                if not os.path.exists(activate_path):
                    error_msg = f"activate: {activate_path}: No such file or directory"
                    self.ui.display_error(command, error_msg)
                    self.context_manager.add_shell_context(command, error_msg)
                    return

                bash_command = f'source "{activate_path}" && env'
                self._execute_source_like_command(command, bash_command)

        except Exception as error:
            error_msg = f"activate: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)

    def _handle_interactive_command(self, command: str) -> None:
        if self._has_background_execution(command):
            self._execute_background_command(command)
            return

        if self._should_stream_interactive_command(command):
            handled = self._handle_streaming_interactive_command(command)
            if handled:
                return

        self._handle_passthrough_interactive_command(command)

    def _handle_passthrough_interactive_command(self, command: str) -> None:
        try:
            self.ui.display_interactive_start(command)

            shell_kwargs = {}
            if os.name != "nt":
                shell_kwargs["executable"] = Config.get_shell()

            result = subprocess.run(
                command,
                shell=True,
                cwd=os.getcwd(),
                **shell_kwargs,
            )

            self.ui.display_interactive_end(command, result.returncode)

            context_msg = (
                f"Interactive command completed with exit code: {result.returncode}"
            )
            self.context_manager.add_shell_context(command, context_msg)

        except KeyboardInterrupt:
            self.ui.display_interrupt("Interactive mode interrupted")
            self.context_manager.add_shell_context(
                command, "Interactive command interrupted by user"
            )
        except Exception as error:
            error_msg = f"Error running interactive command: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)

    def _execute_background_command(self, command: str) -> None:
        try:
            stripped = command.rstrip()
            if not stripped:
                self.ui.display_error(command, "Empty command")
                return

            i = len(stripped) - 1
            if i < 0 or stripped[i] != "&":
                self._handle_passthrough_interactive_command(command)
                return

            if i > 0 and stripped[i - 1] == "&":
                self._handle_passthrough_interactive_command(command)
                return

            cmd_to_run = stripped[:i].rstrip()

            if not cmd_to_run:
                self.ui.display_error(command, "Empty command after removing &")
                return

            job_id = self.next_job_id
            self.next_job_id += 1

            shell_kwargs = {}
            if os.name != "nt":
                shell_kwargs["executable"] = Config.get_shell()

            def set_process_group():
                try:
                    os.setpgid(0, 0)
                except Exception:
                    pass

            process = subprocess.Popen(
                cmd_to_run,
                shell=True,
                cwd=os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=set_process_group if os.name != "nt" else None,
                start_new_session=False,
                **shell_kwargs,
            )

            pgid = None
            try:
                if os.name != "nt":
                    pgid = os.getpgid(process.pid)
            except Exception:
                pass

            self.jobs[job_id] = {
                "id": job_id,
                "pid": process.pid,
                "pgid": pgid,
                "process": process,
                "command": cmd_to_run,
                "status": "running",
                "start_time": time.time(),
            }

            self.task_queue.appendleft(job_id)

            self.console.print(f"[green][{job_id}] {process.pid}[/green]")
            self.console.print(f"[dim]Started: {cmd_to_run}[/dim]")

            self.context_manager.add_shell_context(
                command, f"Background job [{job_id}] started with PID {process.pid}"
            )

            self._monitor_background_job(job_id, process)

        except Exception as error:
            error_msg = f"Failed to start background job: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)

    def _monitor_background_job(self, job_id: int, process: subprocess.Popen) -> None:
        import threading

        def monitor():
            try:
                while True:
                    if job_id not in self.jobs:
                        break

                    exit_code = process.poll()
                    if exit_code is not None:
                        if job_id in self.jobs:
                            self.jobs[job_id]["status"] = "done"
                            self.jobs[job_id]["exit_code"] = exit_code
                            self.jobs[job_id]["completion_time"] = time.time()

                            if exit_code == 0:
                                status_msg = f"[green][{job_id}] Done[/green]"
                            else:
                                status_msg = (
                                    f"[yellow][{job_id}] Exit {exit_code}[/yellow]"
                                )

                            def show_completion():
                                self.console.print(f"\n{status_msg}")
                                self.console.print(
                                    f"[dim]Completed: {self.jobs[job_id]['command']}[/dim]"
                                )

                            try:
                                if sys.stdout:
                                    show_completion()
                            except Exception:
                                pass
                        break

                    if (
                        job_id in self.jobs
                        and self.jobs[job_id].get("status") == "stopped"
                    ):
                        break

                    time.sleep(0.5)

            except Exception:
                if job_id in self.jobs:
                    self.jobs[job_id]["status"] = "failed"

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def _handle_job_control_command(self, command: str) -> None:
        parts = command.strip().split()
        if not parts:
            return

        cmd = parts[0]

        if cmd == "jobs":
            self._show_jobs_list()
            return

        if cmd in {"fg", "bg"}:
            if len(parts) < 2:
                if cmd == "fg":
                    job_id = None
                    for jid in self.task_queue:
                        job_info = self.jobs.get(jid)
                        if job_info and job_info.get("status") in [
                            "running",
                            "stopped",
                        ]:
                            job_id = jid
                            break
                else:
                    job_id = None
                    for jid in self.task_queue:
                        job_info = self.jobs.get(jid)
                        if job_info and job_info.get("status") == "stopped":
                            job_id = jid
                            break

                if job_id is None:
                    status_type = "running or stopped" if cmd == "fg" else "stopped"
                    self.ui.display_error(command, f"{cmd}: no {status_type} job found")
                    self.console.print(
                        f"Usage: {cmd} [%<jobid>] or use 'jobs' to list jobs"
                    )
                    return
            else:
                job_spec = parts[1]
                job_id = self._parse_job_spec(job_spec)
                if job_id is None:
                    self.ui.display_error(command, f"{cmd}: no such job")
                    return

            if cmd == "fg":
                self._bring_job_to_foreground(job_id)
            else:
                self._resume_background_job(job_id)

            return

        self.ui.display_error(command, f"Unknown job control command: {cmd}")

    def _set_foreground_process_group(self, pgid: int) -> bool:
        if os.name == "nt":
            return False

        try:
            import termios

            fd = sys.stdin.fileno()
            old_termios = termios.tcgetattr(fd)

            os.tcsetpgrp(fd, pgid)

            if not hasattr(self, "_saved_terminal"):
                self._saved_terminal = {
                    "fd": fd,
                    "termios": old_termios,
                    "foreground_pgid": os.tcgetpgrp(fd),
                }

            return True
        except Exception:
            return False

    def _restore_terminal_control(self) -> bool:
        if os.name == "nt" or not hasattr(self, "_saved_terminal"):
            return False

        try:
            import termios

            saved = self._saved_terminal

            os.tcsetpgrp(saved["fd"], os.getpgid(os.getpid()))

            termios.tcsetattr(saved["fd"], termios.TCSADRAIN, saved["termios"])
            return True
        except Exception:
            return False

    def _send_signal_to_job(self, job_id: int, sig: int) -> bool:
        if job_id not in self.jobs:
            return False

        job_info = self.jobs[job_id]
        pgid = job_info.get("pgid")
        pid = job_info.get("pid")

        if not pgid or not pid:
            return False

        try:
            os.killpg(pgid, sig)
            return True
        except Exception:
            try:
                os.kill(pid, sig)
                return True
            except Exception:
                return False

    def _suspend_foreground_job(self) -> bool:
        if not self.foreground_job:
            return False

        job_id = self.foreground_job
        if job_id not in self.jobs:
            self.foreground_job = None
            return False

        job_info = self.jobs[job_id]
        if job_info.get("status") != "running":
            return False

        if self._send_signal_to_job(job_id, signal.SIGTSTP):
            job_info["status"] = "stopped"
            self.console.print(f"\n[yellow][{job_id}] Stopped[/yellow]")
            self.console.print(
                f"[dim]Job suspended. Use 'bg %{job_id}' to resume in background[/dim]"
            )
            self.console.print(f"[dim]or 'fg %{job_id}' to resume in foreground[/dim]")

            if os.name != "nt":
                self._restore_terminal_control()

            self.foreground_job = None
            return True

        return False

    def _interrupt_foreground_job(self) -> bool:
        if not self.foreground_job:
            return False

        job_id = self.foreground_job
        if job_id not in self.jobs:
            self.foreground_job = None
            return False

        job_info = self.jobs[job_id]
        if job_info.get("status") != "running":
            return False

        if self._send_signal_to_job(job_id, signal.SIGINT):
            self.console.print(f"\n[yellow][{job_id}] Interrupted[/yellow]")
            self.console.print(f"[dim]Job interrupted with SIGINT[/dim]")

            if os.name != "nt":
                self._restore_terminal_control()

            return True

        return False

    def _cleanup_all_jobs(self) -> None:
        if not self.jobs:
            return

        self.console.print("[dim]Cleaning up background jobs...[/dim]")

        for job_id, job_info in list(self.jobs.items()):
            status = job_info.get("status")
            if status in ["running", "stopped"]:
                pid = job_info.get("pid")
                command = job_info.get("command", "unknown")

                self.console.print(
                    f"[dim]Terminating job [{job_id}] (PID: {pid}): {command}[/dim]"
                )

                try:
                    if self._send_signal_to_job(job_id, signal.SIGTERM):
                        time.sleep(0.1)

                        if job_info.get("process"):
                            exit_code = job_info["process"].poll()
                            if exit_code is None:
                                self._send_signal_to_job(job_id, signal.SIGKILL)
                                self.console.print(
                                    f"[yellow]Job [{job_id}] required SIGKILL[/yellow]"
                                )
                            else:
                                self.console.print(
                                    f"[dim]Job [{job_id}] terminated[/dim]"
                                )
                        else:
                            self.console.print(f"[dim]Job [{job_id}] terminated[/dim]")
                    else:
                        self.console.print(
                            f"[yellow]Failed to send signal to job [{job_id}][/yellow]"
                        )
                except Exception as error:
                    self.console.print(
                        f"[yellow]Error cleaning up job [{job_id}]: {error}[/yellow]"
                    )

                job_info["status"] = "done"
                job_info["exit_code"] = -1

        self.console.print("[dim]Job cleanup completed[/dim]")

    def _show_jobs_list(self) -> None:
        if not self.jobs:
            self.console.print("[dim]No jobs running[/dim]")
            return

        from rich.table import Table

        table = Table(title="Jobs", show_header=True)
        table.add_column("ID", style="cyan", width=6)
        table.add_column("PID", style="green", width=8)
        table.add_column("Status", style="yellow", width=12)
        table.add_column("Command", style="white")

        for job_id in self.task_queue:
            job_info = self.jobs.get(job_id)
            if not job_info:
                continue

            status = job_info.get("status", "unknown")
            status_style = {
                "running": "[green]running[/green]",
                "done": "[dim]done[/dim]",
                "failed": "[red]failed[/red]",
                "stopped": "[yellow]stopped[/yellow]",
            }.get(status, f"[white]{status}[/white]")

            table.add_row(
                f"[{job_id}]",
                str(job_info.get("pid", "N/A")),
                status_style,
                job_info.get("command", "unknown")[:60]
                + ("..." if len(job_info.get("command", "")) > 60 else ""),
            )

        self.console.print(table)

    def _parse_job_spec(self, spec: str) -> Optional[int]:
        spec = spec.strip()

        if spec == "+" or spec == "%+":
            if self.task_queue:
                return self.task_queue[0]
            return None
        elif spec == "-" or spec == "%-":
            if len(self.task_queue) > 1:
                return self.task_queue[1]
            return None

        if spec.startswith("%"):
            spec = spec[1:]

        if not spec:
            return None

        try:
            job_id = int(spec)
            if job_id in self.jobs:
                return job_id
        except ValueError:
            pass

        return None

    def _bring_job_to_foreground(self, job_id: int) -> None:
        if job_id not in self.jobs:
            self.ui.display_error("fg", f"No such job: {job_id}")
            return

        job_info = self.jobs[job_id]
        status = job_info.get("status")

        if status == "done" or status == "failed":
            self.ui.display_error("fg", f"Job {job_id} has already completed")
            return

        self.console.print(f"[yellow]Bringing job [{job_id}] to foreground...[/yellow]")
        self.console.print(
            f"[dim]PID: {job_info['pid']}, Command: {job_info['command']}[/dim]"
        )

        self.foreground_job = job_id

        try:
            process = job_info.get("process")
            if not process:
                self.ui.display_error("fg", f"Job {job_id} has no process object")
                return

            if status == "stopped":
                self.console.print("[dim]Job is stopped, sending SIGCONT...[/dim]")
                if self._send_signal_to_job(job_id, signal.SIGCONT):
                    job_info["status"] = "running"

            pgid = job_info.get("pgid")
            if pgid and os.name != "nt":
                if self._set_foreground_process_group(pgid):
                    self.console.print("[dim]Terminal control transferred to job[/dim]")

            self.console.print(
                "[dim]Job running in foreground (press Ctrl+Z to suspend)[/dim]"
            )
            process.wait()

            if pgid and os.name != "nt":
                self._restore_terminal_control()

            exit_code = process.returncode
            self.foreground_job = None

            if exit_code == 0:
                self.console.print(
                    f"[green]Job [{job_id}] completed successfully[/green]"
                )
            else:
                self.console.print(
                    f"[yellow]Job [{job_id}] exited with code {exit_code}[/yellow]"
                )

            job_info["status"] = "done"
            job_info["exit_code"] = exit_code

        except Exception as error:
            if os.name != "nt":
                self._restore_terminal_control()
            self.foreground_job = None
            self.ui.display_error("fg", f"Error: {error}")

    def _resume_background_job(self, job_id: int) -> None:
        if job_id not in self.jobs:
            self.ui.display_error("bg", f"No such job: {job_id}")
            return

        job_info = self.jobs[job_id]
        status = job_info.get("status")

        if status == "done" or status == "failed":
            self.ui.display_error("bg", f"Job {job_id} has already completed")
            return

        if status != "stopped":
            self.console.print(
                f"[yellow]Job [{job_id}] is not stopped (status: {status})[/yellow]"
            )
            self.console.print(
                f"[dim]PID: {job_info['pid']}, Command: {job_info['command']}[/dim]"
            )
            return

        self.console.print(f"[green]Resuming job [{job_id}] in background...[/green]")
        self.console.print(
            f"[dim]PID: {job_info['pid']}, Command: {job_info['command']}[/dim]"
        )

        if self._send_signal_to_job(job_id, signal.SIGCONT):
            job_info["status"] = "running"
            self.console.print(f"[green]Job [{job_id}] resumed in background[/green]")
        else:
            self.ui.display_error("bg", f"Failed to resume job {job_id}")

    def _should_stream_interactive_command(self, command: str) -> bool:
        parts = command.strip().split()
        if not parts:
            return False

        base_cmd = parts[0]
        if base_cmd == "sudo" and len(parts) > 1:
            base_cmd = parts[1]

        base_cmd = os.path.basename(base_cmd)
        return base_cmd in getattr(Config, "STREAMING_COMMANDS", set())

    def _handle_streaming_interactive_command(self, command: str) -> bool:
        if os.name == "nt":
            return False

        try:
            process = self._spawn_streaming_process(command)
        except KeyboardInterrupt:
            self.console.print("[yellow] Command cancelled.[/yellow]")
            return True
        except Exception as error:
            self.ui.display_error(command, f"Streaming setup failed: {error}")
            return False

        if process is None:
            return True

        try:
            output, exit_code, cancelled = self.streaming_ui.stream_shell_command(
                command, process
            )
        finally:
            if process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            if process.stdin:
                try:
                    process.stdin.close()
                except Exception:
                    pass

        if cancelled:
            self.context_manager.add_shell_context(
                command, "Streaming command cancelled by user"
            )
            return True

        exit_display = exit_code if exit_code is not None else "unknown"
        context_output = output or f"Exit code: {exit_display}"
        self.context_manager.add_shell_context(command, context_output)
        return True

    def _spawn_streaming_process(self, command: str) -> subprocess.Popen | None:
        shell_env = os.environ.copy()
        shell_kwargs = {}
        if os.name != "nt":
            shell_kwargs["executable"] = Config.get_shell()

        sanitized_command = command
        password: str | None = None

        if command.strip().startswith("sudo "):
            password = self._prompt_sudo_password()
            if password is None:
                self.console.print(
                    "[yellow]Cancelled command: sudo password not provided.[/yellow]"
                )
                return None
            parts = command.strip().split(maxsplit=1)
            rest = parts[1] if len(parts) > 1 else ""
            if not rest:
                self.console.print("[red]sudo requires a command to execute.[/red]")
                return None
            sanitized_command = f"sudo -S {rest}".strip()

        process = subprocess.Popen(
            sanitized_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=False,
            bufsize=0,
            cwd=os.getcwd(),
            env=shell_env,
            **shell_kwargs,
        )

        if password is not None and process.stdin:
            try:
                process.stdin.write((password + "\n").encode())
                process.stdin.flush()
            except Exception:
                pass

        return process

    def _prompt_sudo_password(self) -> str | None:
        try:
            from prompt_toolkit import prompt as pt_prompt

            return pt_prompt("sudo password: ", is_password=True).strip() or None
        except KeyboardInterrupt:
            return None
        except Exception:
            try:
                from getpass import getpass

                return getpass("sudo password: ") or None
            except Exception:
                return None

    def _handle_regular_command(self, command: str) -> None:
        bash_builtins = [
            "source",
            "export",
            "unset",
            "alias",
            "unalias",
            "declare",
            "typeset",
            "readonly",
        ]
        command_parts = command.strip().split()
        base_command = command_parts[0] if command_parts else ""

        needs_shell_invocation = (
            "source " in command
            or command.startswith("source")
            or base_command in bash_builtins
            or "&&" in command
            or "||" in command
            or ";" in command
            or "export " in command
            or "unset " in command
            or self._has_shell_operator(command)
            or self._contains_glob_pattern(command)
        )

        shell_env = os.environ.copy()
        shell_kwargs = {}
        if os.name != "nt":
            shell_kwargs["executable"] = Config.get_shell()

        has_redirection_or_pipe = self._has_shell_redirection(command)

        if needs_shell_invocation:
            with self.ui.create_status(f"Executing: {command}"):
                result = subprocess.run(
                    self._build_shell_invocation(command),
                    capture_output=True,
                    text=True,
                    cwd=os.getcwd(),
                    env=shell_env,
                )
        else:
            with self.ui.create_status(f"Executing: {command}"):
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=os.getcwd(),
                    env=shell_env,
                    **shell_kwargs,
                )

        if (
            has_redirection_or_pipe
            and not result.stdout.strip()
            and not result.stderr.strip()
        ):
            pass
        else:
            if self._is_command_not_found(result):
                base_cmd = self._extract_base_command(command)
                suggestions = self._suggest_command_alternatives(base_cmd)
                self.ui.display_command_not_found(
                    command,
                    base_cmd,
                    result.stderr or result.stdout or "command not found",
                    suggestions,
                )
            elif result.returncode != 0 and result.stderr:
                error_msg = (
                    result.stderr.strip()
                    or f"Command failed with exit code {result.returncode}"
                )
                self.ui.display_error(command, error_msg)
            else:
                self.ui.display_shell_output(command, result)

        output = result.stdout + result.stderr
        self.context_manager.add_shell_context(command, output)
        self._update_completion_if_needed(command)

    def _handle_files_command(self, command: str) -> None:
        try:
            tokens = shlex.split(command)
        except ValueError as error:
            error_msg = f"files: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)
            return

        path = os.getcwd()
        show_hidden = False
        preview_target: Optional[str] = None
        max_entries = 20
        positional_set = False

        token_iter = iter(tokens[1:])
        for token in token_iter:
            if token in {"-a", "--all"}:
                show_hidden = True
                continue
            if token in {"-p", "--preview"}:
                try:
                    preview_target = next(token_iter)
                except StopIteration:
                    error_msg = "files: --preview requires a file path"
                    self.ui.display_error(command, error_msg)
                    self.context_manager.add_shell_context(command, error_msg)
                    return
                continue
            if token.startswith("--preview="):
                preview_target = token.split("=", 1)[1]
                continue
            if token in {"-m", "--max"}:
                try:
                    max_value = next(token_iter)
                    max_entries = max(5, min(100, int(max_value)))
                except (StopIteration, ValueError):
                    error_msg = "files: --max requires an integer between 5-100"
                    self.ui.display_error(command, error_msg)
                    self.context_manager.add_shell_context(command, error_msg)
                    return
                continue
            if token.startswith("--max="):
                try:
                    max_entries = max(5, min(100, int(token.split("=", 1)[1])))
                except ValueError:
                    error_msg = "files: invalid --max value"
                    self.ui.display_error(command, error_msg)
                    self.context_manager.add_shell_context(command, error_msg)
                    return
                continue
            if token.startswith("-"):
                error_msg = f"files: unknown option '{token}'"
                self.ui.display_error(command, error_msg)
                self.context_manager.add_shell_context(command, error_msg)
                return

            if positional_set:
                error_msg = "files: multiple paths provided"
                self.ui.display_error(command, error_msg)
                self.context_manager.add_shell_context(command, error_msg)
                return

            resolved = os.path.expanduser(token)
            if not os.path.isabs(resolved):
                resolved = os.path.join(os.getcwd(), resolved)
            path = os.path.abspath(resolved)
            positional_set = True

        if not os.path.exists(path):
            error_msg = f"files: path not found: {path}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)
            return

        if not os.path.isdir(path):
            error_msg = f"files: not a directory: {path}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)
            return

        try:
            directories: List[Dict[str, str]] = []
            files: List[Dict[str, str]] = []
            with os.scandir(path) as entries:
                for entry in entries:
                    if not show_hidden and entry.name.startswith("."):
                        continue
                    try:
                        stat_info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue

                    item = {
                        "name": entry.name,
                        "path": entry.path,
                        "mtime": datetime.fromtimestamp(stat_info.st_mtime).strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                        "size": stat_info.st_size,
                    }

                    if entry.is_dir(follow_symlinks=False):
                        directories.append(item)
                    else:
                        files.append(item)
        except OSError as error:
            error_msg = f"files: {error}"
            self.ui.display_error(command, error_msg)
            self.context_manager.add_shell_context(command, error_msg)
            return

        directories.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["name"].lower())

        dir_total = len(directories)
        file_total = len(files)
        directories_display = directories[:max_entries]
        files_display = files[:max_entries]

        preview_path = None
        if preview_target:
            candidate = preview_target
            candidate = os.path.expanduser(candidate)
            if not os.path.isabs(candidate):
                candidate = os.path.join(path, candidate)
            candidate = os.path.abspath(candidate)
            if os.path.isfile(candidate):
                preview_path = candidate
        elif files:
            preview_path = files[0]["path"]

        preview_data = self._build_file_preview(preview_path) if preview_path else None

        self.ui.display_file_explorer(
            base_path=path,
            directories=directories_display,
            files=files_display,
            preview=preview_data,
            dir_total=dir_total,
            file_total=file_total,
            show_hidden=show_hidden,
        )

        summary = f"files: {dir_total} dirs, {file_total} files in {path}"
        if preview_data and preview_data.get("path"):
            summary += f" | preview: {os.path.basename(preview_data['path'])}"
        self.context_manager.add_shell_context(command, summary)

    def _build_file_preview(self, file_path: str | None) -> Optional[Dict[str, str]]:
        if not file_path:
            return None

        if not os.path.isfile(file_path):
            return {"path": file_path, "error": "preview target is not a file"}

        max_bytes = 4000
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read(max_bytes + 1)
        except OSError as error:
            return {"path": file_path, "error": str(error)}

        truncated = len(content) > max_bytes
        if truncated:
            content = content[:max_bytes] + "\n... (truncated)"

        ext = os.path.splitext(file_path)[1].lower()
        language = Config.SYNTAX_EXTENSIONS.get(ext, "text")

        return {
            "path": file_path,
            "content": content,
            "language": language,
            "truncated": "true" if truncated else "false",
        }

    def _update_completion_if_needed(self, command: str) -> None:
        modify_commands = ["touch", "mkdir", "rm", "rmdir", "mv", "cp", "ln"]
        base_cmd = command.strip().split()[0]

        if base_cmd in modify_commands:
            self.completion_manager.update_cache()

    def _execute_source_like_command(
        self, original_command: str, bash_command: str
    ) -> None:
        try:
            old_env = dict(os.environ)

            with self.ui.create_status(f"Executing: {original_command}"):
                result = subprocess.run(
                    self._build_shell_invocation(bash_command),
                    capture_output=True,
                    text=True,
                    cwd=os.getcwd(),
                )

            if result.returncode == 0:
                new_vars: dict[str, str] = {}
                changed_vars: dict[str, dict[str, str]] = {}

                for line in result.stdout.split("\n"):
                    if "=" in line and not line.startswith("_="):
                        try:
                            key, value = line.split("=", 1)
                        except ValueError:
                            continue

                        if key in ["PS1", "PS2", "BASH_FUNC_*", "_"] or key.startswith(
                            "BASH_FUNC_"
                        ):
                            continue

                        if key not in old_env:
                            new_vars[key] = value
                        elif old_env[key] != value:
                            changed_vars[key] = {"old": old_env[key], "new": value}

                        os.environ[key] = value

                success_msg = f" {original_command} completed successfully"
                if new_vars or changed_vars:
                    success_msg += (
                        f" ({len(new_vars)} new, {len(changed_vars)} changed variables)"
                    )

                self.console.print(f"[green]{success_msg}[/green]")
                self.context_manager.add_shell_context(original_command, success_msg)
                self._show_env_changes(new_vars, changed_vars)

            else:
                error_msg = (
                    f"{original_command}: {result.stderr.strip() or 'command failed'}"
                )
                self.ui.display_error(original_command, error_msg)
                self.context_manager.add_shell_context(original_command, error_msg)

        except Exception as error:
            error_msg = f"{original_command}: {error}"
            self.ui.display_error(original_command, error_msg)
            self.context_manager.add_shell_context(original_command, error_msg)

    def _show_env_changes(self, new_vars: dict, changed_vars: dict) -> None:
        important_vars = [
            "PATH",
            "VIRTUAL_ENV",
            "CONDA_DEFAULT_ENV",
            "NODE_ENV",
            "PYTHONPATH",
            "LD_LIBRARY_PATH",
            "JAVA_HOME",
        ]

        if new_vars:
            self.console.print("[dim]New environment variables:[/dim]")
            count = 0
            for var, value in new_vars.items():
                if var in important_vars or count < 5:
                    display_value = value
                    if len(display_value) > 60:
                        display_value = display_value[:57] + "..."
                    self.console.print(
                        f"[dim green]  +{var}={display_value}[/dim green]"
                    )
                    count += 1

            if len(new_vars) > count:
                self.console.print(
                    f"[dim]  ... and {len(new_vars) - count} more new variables[/dim]"
                )

        if changed_vars:
            self.console.print("[dim]Changed environment variables:[/dim]")
            count = 0
            for var, values in changed_vars.items():
                if var in important_vars or count < 3:
                    old_val = values["old"]
                    new_val = values["new"]

                    if len(old_val) > 30:
                        old_val = old_val[:27] + "..."
                    if len(new_val) > 30:
                        new_val = new_val[:27] + "..."

                    self.console.print(
                        f"[dim yellow]  ~{var}: {old_val} → {new_val}[/dim yellow]"
                    )
                    count += 1

            if len(changed_vars) > count:
                self.console.print(
                    f"[dim]  ... and {len(changed_vars) - count} more changed variables[/dim]"
                )

    def _build_shell_invocation(self, command: str) -> list[str]:
        shell_path = Config.get_shell()
        if os.name == "nt":
            return [shell_path, "/C", command]
        return [shell_path, "-c", command]

    def _handle_alias_management(self, command: str) -> bool:
        if command == "alias":
            self._display_aliases()
            return True
        if command.startswith("alias "):
            self._handle_alias_command(command)
            return True
        if command.startswith("unalias"):
            self._handle_unalias_command(command)
            return True
        return False

    def _handle_alias_command(self, command: str) -> None:
        try:
            tokens = shlex.split(command)
        except ValueError as error:
            self.ui.display_error(command, f"alias: {error}")
            return

        if len(tokens) == 1:
            self._display_aliases()
            return

        updates: Dict[str, str] = {}
        for token in tokens[1:]:
            if "=" not in token:
                self.ui.display_error(command, f"alias: invalid definition '{token}'")
                return
            name, value = token.split("=", 1)
            value = value.strip("'\"")
            if not self._is_valid_identifier(name):
                self.ui.display_error(command, f"alias: invalid name '{name}'")
                return
            updates[name] = value

        self.aliases.update(updates)
        self._save_aliases()
        self._available_commands_cache = None
        self.console.print(
            f"[green]Aliases updated:[/green] {', '.join(updates.keys())}"
        )

    def _handle_unalias_command(self, command: str) -> None:
        try:
            tokens = shlex.split(command)
        except ValueError as error:
            self.ui.display_error(command, f"unalias: {error}")
            return

        if len(tokens) < 2:
            self.ui.display_error(command, "unalias: requires a name")
            return

        removed: List[str] = []
        for name in tokens[1:]:
            if name in self.aliases:
                removed.append(name)
                del self.aliases[name]

        if removed:
            self._save_aliases()
            self._available_commands_cache = None
            self.console.print(f"[green]Removed aliases:[/green] {', '.join(removed)}")
        else:
            self.console.print("[yellow]No matching aliases removed[/yellow]")

    def _display_aliases(self) -> None:
        if not self.aliases:
            self.console.print("[yellow]No aliases defined[/yellow]")
            return

        table = Table(title="Aliases", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold")
        table.add_column("Value", style="green")
        for name, value in sorted(self.aliases.items()):
            table.add_row(name, value)
        self.console.print(table)

    def _expand_alias(self, command: str) -> str:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            return command

        if not tokens:
            return command

        alias_value = self.aliases.get(tokens[0])
        if not alias_value:
            return command

        rest = " ".join(shlex.quote(token) for token in tokens[1:])
        new_command = f"{alias_value} {rest}".strip()
        return new_command

    def _load_aliases(self) -> Dict[str, str]:
        try:
            if Config.ALIAS_FILE.exists():
                raw = Config.ALIAS_FILE.read_text(encoding="utf-8").strip()
                if raw:
                    return json.loads(raw)
        except Exception:
            pass
        return {}

    def _save_aliases(self) -> None:
        try:
            Config.ALIAS_FILE.write_text(
                json.dumps(self.aliases, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        else:
            self._available_commands_cache = None

    def _handle_export_command(self, command: str) -> bool:
        if not command.startswith("export"):
            return False

        try:
            tokens = shlex.split(command)
        except ValueError as error:
            self.ui.display_error(command, f"export: {error}")
            return True

        if len(tokens) == 1:
            entries = [f"{key}={value}" for key, value in sorted(os.environ.items())]
            self.console.print("\n".join(entries))
            return True

        updates: Dict[str, str] = {}
        for token in tokens[1:]:
            if "=" not in token:
                self.ui.display_error(command, f"export: invalid assignment '{token}'")
                return True
            name, value = token.split("=", 1)
            if not self._is_valid_identifier(name):
                self.ui.display_error(command, f"export: invalid name '{name}'")
                return True
            updates[name] = value

        for name, value in updates.items():
            os.environ[name] = value

        self.console.print(f"[green]Exported:[/green] {', '.join(updates.keys())}")
        return True

    def _handle_unset_command(self, command: str) -> bool:
        if not command.startswith("unset "):
            return False

        try:
            tokens = shlex.split(command)
        except ValueError as error:
            self.ui.display_error(command, f"unset: {error}")
            return True

        if len(tokens) < 2:
            self.ui.display_error(command, "unset: requires a variable name")
            return True

        removed: List[str] = []
        for name in tokens[1:]:
            if name in os.environ:
                removed.append(name)
                del os.environ[name]

        if removed:
            self.console.print(f"[green]Unset:[/green] {', '.join(removed)}")
        else:
            self.console.print("[yellow]No variables unset[/yellow]")
        return True

    def _handle_assignment_only(self, command: str) -> bool:
        if "=" not in command or command.startswith("alias"):
            return False

        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = []

        if not tokens:
            return False

        all_have_equal = all("=" in token for token in tokens)

        if all_have_equal:
            assignments: Dict[str, str] = {}
            for token in tokens:
                if "=" not in token:
                    return False
                name, value = token.split("=", 1)
                if not self._is_valid_identifier(name):
                    return False

                if "$((" in value and "))" in value:
                    evaluated_value = self._evaluate_arithmetic_expression(value, name)
                    if evaluated_value is not None:
                        assignments[name] = evaluated_value
                    else:
                        assignments[name] = value
                else:
                    assignments[name] = value

            for name, value in assignments.items():
                os.environ[name] = value

            self.console.print(
                f"[green]Set variables:[/green] {', '.join(assignments.keys())}"
            )
            return True
        else:
            if len(tokens) >= 1 and "=" in tokens[0]:
                first_token = tokens[0]
                if "=" in first_token:
                    name, partial_value = first_token.split("=", 1)
                    if not self._is_valid_identifier(name):
                        return False

                    full_value_parts = [partial_value] + tokens[1:]
                    full_value = " ".join(full_value_parts)

                    if "$((" in full_value and "))" in full_value:
                        evaluated_value = self._evaluate_arithmetic_expression(
                            full_value, name
                        )
                        if evaluated_value is not None:
                            os.environ[name] = evaluated_value
                            self.console.print(f"[green]Set variables:[/green] {name}")
                            return True

            return False

    def _evaluate_arithmetic_expression(
        self, expression: str, var_name: str = ""
    ) -> Optional[str]:
        try:
            import re

            pattern = r"\$\(\(([^)]+)\)\)"
            match = re.search(pattern, expression)
            if not match:
                return expression

            arithmetic_expr = match.group(1)

            env_copy = os.environ.copy()

            bash_cmd = f"echo $(({arithmetic_expr}))"

            result = subprocess.run(
                ["bash", "-c", bash_cmd],
                capture_output=True,
                text=True,
                env=env_copy,
                cwd=os.getcwd(),
                timeout=2,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                self.console.print(
                    f"[yellow]Warning: Failed to evaluate arithmetic expression: {expression}[/yellow]"
                )
                if result.stderr:
                    self.console.print(f"[dim]{result.stderr.strip()}[/dim]")
                return None

        except subprocess.TimeoutExpired:
            self.console.print(
                f"[yellow]Warning: Arithmetic evaluation timed out for: {expression}[/yellow]"
            )
            return None
        except Exception as e:
            self.console.print(
                f"[yellow]Warning: Error evaluating arithmetic: {e}[/yellow]"
            )
            return None

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name))

    def _handle_config_reload_command(self) -> None:
        try:
            success = Config.reload()
            if success:
                self.refresh_configuration()
                self.console.print(
                    PanelTheme.build(
                        f"[green]Configuration reloaded from[/green] [cyan]{Config.CONFIG_FILE}[/cyan]",
                        title="Config",
                        style="success",
                        fit=True,
                    )
                )
            else:
                self.console.print(
                    PanelTheme.build(
                        "[red]Failed to reload configuration[/red]",
                        title="Config",
                        style="error",
                        fit=True,
                    )
                )
        except Exception as e:
            self.console.print(
                PanelTheme.build(
                    f"[red]Error reloading configuration: {e}[/red]",
                    title="Config",
                    style="error",
                    fit=True,
                )
            )

    def _handle_cleanup_memory_command(self) -> None:
        try:
            import gc
            import sys

            initial_stats = self._get_memory_stats()
            cleanup_result = self._perform_memory_cleanup()
            final_stats = self._get_memory_stats()

            freed_mb = max(0, initial_stats["rss_mb"] - final_stats["rss_mb"])
            cleanup_result["freed_mb"] = freed_mb

            self._display_cleanup_results(initial_stats, final_stats, cleanup_result)

            self.context_manager.add_shell_context(
                "/cleanup_memory", f"Memory cleanup performed. Freed: {freed_mb:.1f}MB"
            )

        except ImportError:
            import gc

            gc.collect()
            self.console.print(
                PanelTheme.build(
                    "[green]Memory cleanup completed[/green]\n"
                    "[dim]Cleared: completion cache, command cache, script cache[/dim]",
                    title="Memory Cleanup",
                    style="success",
                )
            )
        except Exception as e:
            self.console.print(
                PanelTheme.build(
                    f"[red]Error during memory cleanup: {e}[/red]",
                    title="Memory Cleanup",
                    style="error",
                )
            )

    def _get_memory_stats(self):
        import os
        import sys

        stats = {
            "rss_mb": 0,
            "vms_mb": 0,
            "shared_mb": 0,
            "python_objects": 0,
            "context_entries": 0,
        }

        if hasattr(self.context_manager, "shell_context"):
            stats["context_entries"] = len(self.context_manager.shell_context)

        try:
            import psutil
            import gc

            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            stats["rss_mb"] = memory_info.rss / 1024 / 1024
            stats["vms_mb"] = memory_info.vms / 1024 / 1024
            if hasattr(memory_info, "shared"):
                stats["shared_mb"] = memory_info.shared / 1024 / 1024

            if "gc" in sys.modules:
                stats["python_objects"] = len(gc.get_objects())

        except ImportError:
            pass
        except Exception:
            pass

        return stats

    def _perform_memory_cleanup(self):
        import gc
        import sys

        results = {
            "freed_mb": 0,
            "context_trimmed": 0,
            "gc_collected": 0,
            "cache_cleared": False,
        }

        if hasattr(self.completion_manager, "clear_cache"):
            self.completion_manager.clear_cache()
            results["cache_cleared"] = True

        self._available_commands_cache = None

        if hasattr(self.script_runtime, "clear_cache"):
            self.script_runtime.clear_cache()

        if hasattr(self.context_manager, "clear_all"):
            self.context_manager.clear_all()

        gc.collect()
        results["gc_collected"] = gc.collect()

        return results

    def _display_cleanup_results(self, initial, final, cleanup_result):
        from rich import box

        try:
            table = Table(
                title="Memory Cleanup Results",
                show_header=True,
                header_style="bold cyan",
                box=box.ROUNDED,
            )
            table.add_column("Metric", style="cyan")
            table.add_column("Before", style="yellow")
            table.add_column("After", style="green")
            table.add_column("Change", style="magenta")

            rss_change = final["rss_mb"] - initial["rss_mb"]
            table.add_row(
                "RSS Memory (MB)",
                f"{initial['rss_mb']:.1f}",
                f"{final['rss_mb']:.1f}",
                f"{rss_change:+.1f}" if rss_change < 0 else f"{rss_change:+.1f}",
            )

            objects_change = final["python_objects"] - initial["python_objects"]
            table.add_row(
                "Python Objects",
                str(initial["python_objects"]),
                str(final["python_objects"]),
                f"{objects_change:+d}"
                if objects_change < 0
                else f"{objects_change:+d}",
            )

            freed_memory = max(0, -rss_change)
            table.add_row(
                "Freed Memory",
                "-",
                f"{freed_memory:.1f} MB" if freed_memory > 0 else "0.0 MB",
                "✅" if freed_memory > 0 else "➖",
            )

            self.console.print(table)

        except NameError:
            self.console.print("[bold cyan]Memory Cleanup Results[/bold cyan]")
            self.console.print(
                f"RSS Memory: {initial['rss_mb']:.1f}MB → {final['rss_mb']:.1f}MB (Change: {final['rss_mb'] - initial['rss_mb']:+.1f}MB)"
            )
            self.console.print(
                f"Freed Memory: {cleanup_result.get('freed_mb', 0):.1f} MB"
            )

        messages = []
        if cleanup_result.get("cache_cleared", False):
            messages.append("Cleared completion cache")

        if self._available_commands_cache is None:
            messages.append("Cleared command cache")

        if hasattr(self.script_runtime, "clear_cache"):
            messages.append("Cleared script cache")

        if cleanup_result.get("gc_collected", 0) > 0:
            messages.append(
                f"Garbage collected {cleanup_result['gc_collected']} objects"
            )

        if messages:
            self.console.print("[dim]" + ", ".join(messages) + "[/dim]")

    @staticmethod
    def _contains_glob_pattern(command: str) -> bool:
        return any(char in command for char in ["*", "?", "["])

    @staticmethod
    def _has_shell_redirection(command: str) -> bool:
        return any(op in command for op in ["|", ">", "<", "2>", "&>", ";", "&&", "||"])

    def _extract_base_command(self, command: str) -> str:
        stripped = command.strip()
        if not stripped:
            return ""
        parts = stripped.split()
        return parts[0] if parts else ""

    def _is_command_not_found(self, result) -> bool:
        if not result:
            return False
        if result.returncode == 127:
            return True
        combined = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
        return "command not found" in combined or "not recognized" in combined

    def _get_available_commands(self) -> set[str]:
        if self._available_commands_cache is not None:
            return self._available_commands_cache

        commands: set[str] = set(self.aliases.keys())
        path_env = os.environ.get("PATH", "")
        for directory in path_env.split(os.pathsep):
            if not directory:
                continue
            try:
                for entry in os.scandir(directory):
                    if not entry.name:
                        continue
                    try:
                        if entry.is_file() and os.access(entry.path, os.X_OK):
                            commands.add(entry.name)
                    except OSError:
                        continue
            except OSError:
                continue

        self._available_commands_cache = commands
        return commands

    def _suggest_command_alternatives(self, base_command: str) -> List[str]:
        if not base_command:
            return []

        candidates = self._get_available_commands()
        suggestions = difflib.get_close_matches(
            base_command, sorted(candidates), n=3, cutoff=0.6
        )
        return suggestions
