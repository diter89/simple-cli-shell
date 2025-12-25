#!/usr/bin/env python3
import configparser
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


class Config:
    # Shell configuration
    MAX_SHELL_CONTEXT = 10

    # Interactive commands that take over the terminal
    INTERACTIVE_COMMANDS = {
        "nano",
        "vim",
        "vi",
        "emacs",
        "mc",
        "htop",
        "top",
        "fzf",
        "less",
        "more",
        "man",
        "tmux",
        "screen",
        "python3",
        "python",
        "node",
        "irb",
        "psql",
        "mysql",
        "nvim",
        "nu",
        "xonsh",
        "apt",
        "sudo",
        "sqlite3",
        "redis-cli",
        "mongo",
        "bash",
        "zsh",
        "fish",
        "jobs",
        "fg",
        "bg",
        "tree",
        "ping",
    }

    # Package manager commands that should stream
    STREAMING_COMMANDS = {
        "apt",
        "apt-get",
        "pip",
        "pip3",
        "npm",
        "pnpm",
        "yarn",
        "poetry",
        "composer",
        "cargo",
        "brew",
        "bundle",
        "go",
        "apk",
        "ping",
    }

    SHELL_STREAM_SUMMARY_PANEL = True
    SHELL_STREAM_OUTPUT_PANEL = True
    CD_FEEDBACK_ENABLED = False

    # Map file extensions to syntax lexers for Rich rendering.
    SYNTAX_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".fish": "fish",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".xml": "xml",
        ".md": "markdown",
        ".txt": "text",
    }

    SYNTAX_HIGHLIGHT_COMMANDS = ["cat", "head", "tail", "batcat", "bat"]
    SYNTAX_THEME = "github-dark"

    LS_COMMANDS = ["ls", "la", "lsd", "ll"]

    FILE_ICONS = {
        "directory": "",
        "file": "",
        "executable": "",
        "symlink": "",
        "image": "",
        "video": "󰕧",
        "audio": "",
        "archive": "",
        "document": "󰷈",
        "code": " ",
    }

    FILE_COLORS = {
        "directory": "bold blue",
        "file": "white",
        "executable": "bold green",
        "symlink": "cyan",
        "image": "magenta",
        "video": "red",
        "audio": "yellow",
        "archive": "bold yellow",
        "document": "blue",
        "code": "green",
        "hidden": "dim white",
    }

    FILE_EXTENSIONS = {
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
        ".gif": "image",
        ".bmp": "image",
        ".svg": "image",
        ".webp": "image",
        ".ico": "image",
        ".mp4": "video",
        ".avi": "video",
        ".mkv": "video",
        ".mov": "video",
        ".wmv": "video",
        ".flv": "video",
        ".webm": "video",
        ".m4v": "video",
        ".mp3": "audio",
        ".wav": "audio",
        ".flac": "audio",
        ".aac": "audio",
        ".ogg": "audio",
        ".m4a": "audio",
        ".wma": "audio",
        ".zip": "archive",
        ".rar": "archive",
        ".7z": "archive",
        ".tar": "archive",
        ".gz": "archive",
        ".bz2": "archive",
        ".xz": "archive",
        ".deb": "archive",
        ".rpm": "archive",
        ".dmg": "archive",
        ".pdf": "document",
        ".doc": "document",
        ".docx": "document",
        ".xls": "document",
        ".xlsx": "document",
        ".ppt": "document",
        ".pptx": "document",
        ".txt": "document",
        ".rtf": "document",
        ".odt": "document",
        ".ods": "document",
        ".odp": "document",
        ".py": "code",
        ".js": "code",
        ".html": "code",
        ".css": "code",
        ".java": "code",
        ".cpp": "code",
        ".c": "code",
        ".h": "code",
        ".php": "code",
        ".rb": "code",
        ".go": "code",
        ".rs": "code",
        ".swift": "code",
        ".kt": "code",
        ".scala": "code",
        ".sh": "code",
        ".bash": "code",
        ".zsh": "code",
        ".fish": "code",
        ".json": "code",
        ".xml": "code",
        ".yaml": "code",
        ".yml": "code",
        ".toml": "code",
        ".ini": "code",
        ".cfg": "code",
        ".conf": "code",
        ".sql": "code",
        ".r": "code",
        ".m": "code",
    }

    REFRESH_RATE = 10

    # Controls whether shell selection is automatic or forced to a user choice.
    CHOICE_DEFAULT_SHELL = "auto"

    # Prompt lexer choice ("auto" disables highlighting, otherwise pygments lexer name).
    CHOICE_PROMPT_LEXER = "auto"

    PROMPT_SYMBOL = "❯"
    PROMPT_TEMPLATE_TOP = ""
    PROMPT_TEMPLATE_BOTTOM = ""
    PROMPT_PLACEHOLDER = '<style color="#888888"> </style>'

    CONFIG_DIR = Path.home() / ".simple_cli"
    CONFIG_FILE = CONFIG_DIR / "config.ini"  # Legacy INI format
    CONFIG_JSON_FILE = CONFIG_DIR / "config.json"  # Primary JSON format
    LOG_FILE = CONFIG_DIR / "shell.log"
    ALIAS_FILE = CONFIG_DIR / "aliases.json"
    COMMANDS_DESC_FILE = CONFIG_DIR / "commands_desc.json"

    WELCOME_MESSAGE = "Welcome to Simple-CLI"

    SHOW_STARTUP_BANNER = True

    HELP_KEYBINDS = [
        ("Alt+H", "Show this help"),
        ("Alt+C", "Clear context & conversation"),
        ("Ctrl+C", "Exit application"),
    ]

    HELP_SPECIAL_COMMANDS = [
        ("exit", "Both", "Exit the shell"),
    ]

    PROMPT_STYLES = {
        "left_part": "#c6d0f5",
        "right_part": "#c6d0f5",
        "prompt_padding": "#737994",
        "mode_ai": "#f4b8e4 bold",
        "mode_shell": "#8caaee bold",
        "separator": "#737994",
        "path": "#b5cef8 bold",
        "prompt_symbol": "#f2d5cf bold",
        "clock": "#c6d0f5 bold",
        "status": "#a6d189",
        "prompt_border": "#737994",
        "prompt_os": "#f2d5cf",
        "prompt_folder": "#8caaee bold",
    }

    COMPLETION_STYLES = {
        "completion.menu": "#0a0a0a",
        "scrollbar.background": "bg:#0a7e98 bold",
        "completion-menu.completion": "bg:#0a0a0a fg:#aaaaaa bold",
        "completion-menu.completion fuzzymatch.outside": "#aaaaaa underline",
        "completion-menu.completion fuzzymatch.inside": "fg:#9ece6a bold",
        "completion-menu.completion fuzzymatch.inside.character": "underline bold",
        "completion-menu.completion.current fuzzymatch.outside": "fg:#9ece6a underline",
        "completion-menu.completion.current fuzzymatch.inside": "fg:#f7768e bold",
        "completion-menu.meta.completion": "bg:#0a0a0a fg:#aaaaaa bold",
        "completion-menu.meta.completion.current": "bg:#888888",
    }

    BASH_COMPLETION_FILES = [
        "/usr/share/bash-completion/bash_completion",
        "/etc/bash_completion",
    ]

    BASH_COMPLETION_DIRS = [
        "/usr/share/bash-completion/completions",
        "/etc/bash_completion.d",
    ]

    FISH_COMPLETION_DIRS = [
        "~/.config/fish/completions",
        "/usr/share/fish/completions",
        "/etc/fish/completions",
    ]

    ZSH_COMPLETION_DIRS = [
        "~/.zsh/completions",
        "/usr/share/zsh/functions/Completion",
        "/usr/local/share/zsh/site-functions",
    ]

    NUSHELL_COMPLETION_DIRS = [
        "~/.config/nushell/completions",
    ]

    ENABLED_COMPLETION_SHELLS = ["bash", "fish", "zsh", "nushell"]
    COMPLETION_SHELL_ORDER = ["fish", "zsh", "bash", "nushell"]

    PANEL_STYLES = {
        "default": {
            "border_style": "#888888",
            "padding": (0, 1),
            "title_align": "left",
            "expand": False,
        },
        "info": {
            "border_style": "#8caaee",
            "padding": (0, 1),
            "title_align": "left",
            "expand": False,
        },
        "success": {
            "border_style": "#a6d189",
            "padding": (0, 1),
            "title_align": "left",
            "expand": False,
        },
        "error": {
            "border_style": "#e78284",
            "padding": (0, 1),
            "title_align": "left",
            "expand": False,
        },
        "warning": {
            "border_style": "#e5c890",
            "padding": (0, 1),
            "title_align": "left",
            "expand": False,
        },
    }

    HIGHLIGHTER_ENABLED = True
    HIGHLIGHTER_RULES = [
        {
            "name": "number",
            "pattern": r"(?P<number>\b\d+(?:\.\d+)?\b)",
            "style": "highlight.number",
        },
        {
            "name": "string",
            "pattern": r"(?P<string>\"[^\"]+\")",
            "style": "highlight.string",
        },
        {
            "name": "ip",
            "pattern": r"(?P<ip>\b\d{1,3}(?:\.\d{1,3}){3}\b)",
            "style": "highlight.ip",
        },
    ]
    HIGHLIGHTER_STYLES = {
        "highlight.number": "bold cyan",
        "highlight.string": "bold green",
        "highlight.ip": "bold magenta",
    }

    COMPLETION_AUTO_POPUP = True
    UI_REFRESH_INTERVAL_ENABLED = False

    COMMAND_HIGHLIGHT = {
        "clear": "green" 
    }

    PATH_HIGHLIGHT = {
        "enabled": True,
        "valid_style": "underline cyan",
        "invalid_style": "underline red",
        "create_style": "underline cyan"  # For commands like mkdir, touch
    }

    LEXER_STYLES = {
        "pygments.keyword": "bold #ff79c6",
        "pygments.keyword.namespace": "bold #ff79c6",
        "pygments.keyword.argument": "#ff79c6",
        "pygments.name": "#f8f8f2",
        "pygments.name.builtin": "#8be9fd",
        "pygments.name.function": "#50fa7b",
        "pygments.name.class": "#8be9fd bold",
        "pygments.name.decorator": "#ff79c6",
        "pygments.name.constant": "#bd93f9",
        "pygments.name.attribute": "#50fa7b",
        "pygments.name.variable": "#f8f8f2",
        "pygments.name.namespace": "#8be9fd",
        "pygments.name.module": "#8be9fd",
        "pygments.literal": "#bd93f9",
        "pygments.literal.number": "#bd93f9",
        "pygments.number": "#bd93f9",
        "pygments.string": "#f1fa8c",
        "pygments.literal.string": "#f1fa8c",
        "pygments.literal.string.double": "#f1fa8c",
        "pygments.literal.string.single": "#f1fa8c",
        "pygments.literal.string.docstring": "italic #f1fa8c",
        "pygments.comment": "italic #6272a4",
        "pygments.operator": "#ffb86c",
        "pygments.operator.word": "#ff79c6",
        "pygments.punctuation": "#f8f8f2",
    }

    DEFAULT_SHELL = (
        "/bin/bash" if os.name != "nt" else os.environ.get("COMSPEC", "cmd.exe")
    )

    @classmethod
    def ensure_directories(cls):
        cls.CONFIG_DIR.mkdir(exist_ok=True)

        # Only create/config.json as primary config
        if not cls.CONFIG_JSON_FILE.exists():
            if cls.CONFIG_FILE.exists():
                # Convert existing INI to JSON (one-time migration)
                cls._convert_ini_to_json()
            else:
                # Create default JSON config
                cls._write_default_json_config()

        # DO NOT create config.ini anymore - JSON only
        # config.ini is legacy and will not be created

        if not cls.ALIAS_FILE.exists():
            cls.ALIAS_FILE.write_text("{}", encoding="utf-8")
        cls._ensure_command_descriptions()


    @classmethod
    def get_shell(cls) -> str:
        env_shell = os.getenv("WRAPCLI_SHELL")
        if env_shell:
            return env_shell

        if os.name == "nt":
            return os.getenv("COMSPEC") or cls.DEFAULT_SHELL

        choice_shell = cls._resolve_shell_choice()
        if choice_shell:
            return choice_shell

        return os.getenv("SHELL") or cls.DEFAULT_SHELL

    @classmethod
    def _resolve_shell_choice(cls) -> str | None:
        choice = getattr(cls, "CHOICE_DEFAULT_SHELL", "auto")
        if not choice:
            return None

        normalized = choice.strip()
        if not normalized or normalized.lower() == "auto":
            return None

        expanded = os.path.expanduser(normalized)
        if os.path.isabs(expanded) and os.access(expanded, os.X_OK):
            return expanded

        resolved = shutil.which(normalized)
        if resolved:
            return resolved

        return None

    @classmethod
    def get_prompt_lexer_choice(cls) -> str:
        env_value = os.getenv("HYBRIDSHELL_PROMPT_LEXER")
        if env_value:
            return env_value.strip()
        return getattr(cls, "CHOICE_PROMPT_LEXER", "auto")


    @classmethod
    def is_shell_stream_summary_enabled(cls) -> bool:
        env_value = os.getenv("WRAPCLI_SHELL_STREAM_PANEL")
        if env_value is None:
            return cls.SHELL_STREAM_SUMMARY_PANEL

        normalized = env_value.strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    @classmethod
    def is_shell_stream_output_panel_enabled(cls) -> bool:
        env_value = os.getenv("WRAPCLI_SHELL_STREAM_OUTPUT_PANEL")
        if env_value is None:
            return cls.SHELL_STREAM_OUTPUT_PANEL

        normalized = env_value.strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    @classmethod
    def is_highlighter_enabled(cls) -> bool:
        env_value = os.getenv("HYBRIDSHELL_HIGHLIGHTER")
        if env_value is not None:
            normalized = env_value.strip().lower()
            if normalized in {"0", "false", "no", "off"}:
                return False
            if normalized in {"1", "true", "yes", "on"}:
                return True
        return cls.HIGHLIGHTER_ENABLED

    # ------------------------------------------------------------------
    # External configuration support (config.ini)
    # ------------------------------------------------------------------

    @classmethod
    def _write_default_config(cls) -> None:
        parser = configparser.ConfigParser()

        parser["general"] = {
            "welcome_message": cls.WELCOME_MESSAGE,
            "refresh_rate": str(cls.REFRESH_RATE),
        }

        parser["shell"] = {
            "max_shell_context": str(cls.MAX_SHELL_CONTEXT),
            "interactive_commands": json.dumps(sorted(cls.INTERACTIVE_COMMANDS)),
            "streaming_commands": json.dumps(sorted(cls.STREAMING_COMMANDS)),
            "shell_stream_summary_panel": str(cls.SHELL_STREAM_SUMMARY_PANEL),
            "shell_stream_output_panel": str(cls.SHELL_STREAM_OUTPUT_PANEL),
            "default_shell": cls.DEFAULT_SHELL,
            "choice_default_shell": cls.CHOICE_DEFAULT_SHELL,
        }

        parser["ui"] = {
            "help_keybinds": json.dumps([list(item) for item in cls.HELP_KEYBINDS]),
            "help_special_commands": json.dumps(
                [list(item) for item in cls.HELP_SPECIAL_COMMANDS]
            ),
            "prompt_styles": json.dumps(cls.PROMPT_STYLES),
            "completion_styles": json.dumps(cls.COMPLETION_STYLES),
            "panel_styles": json.dumps(cls.PANEL_STYLES),
            "highlighter_enabled": str(cls.HIGHLIGHTER_ENABLED),
            "highlighter_rules": json.dumps(cls.HIGHLIGHTER_RULES),
            "highlighter_styles": json.dumps(cls.HIGHLIGHTER_STYLES),
            "lexer_styles": json.dumps(cls.LEXER_STYLES),
            "completion_auto_popup": str(cls.COMPLETION_AUTO_POPUP),
            "prompt_symbol": cls.PROMPT_SYMBOL,
            "prompt_template_top": cls.PROMPT_TEMPLATE_TOP,
            "prompt_template_bottom": cls.PROMPT_TEMPLATE_BOTTOM,
            "choice_prompt_lexer": cls.CHOICE_PROMPT_LEXER,
        }

        parser["syntax"] = {
            "syntax_extensions": json.dumps(cls.SYNTAX_EXTENSIONS),
            "syntax_highlight_commands": json.dumps(cls.SYNTAX_HIGHLIGHT_COMMANDS),
            "ls_commands": json.dumps(cls.LS_COMMANDS),
            "file_icons": json.dumps(cls.FILE_ICONS),
            "file_colors": json.dumps(cls.FILE_COLORS),
            "file_extensions": json.dumps(cls.FILE_EXTENSIONS),
            "bash_completion_files": json.dumps(cls.BASH_COMPLETION_FILES),
            "bash_completion_dirs": json.dumps(cls.BASH_COMPLETION_DIRS),
        }

        with cls.CONFIG_FILE.open("w", encoding="utf-8") as config_handle:
            parser.write(config_handle)

    @classmethod
    def _load_external_config(cls) -> None:
        # Load from JSON config only
        # INI config is no longer supported
        cls._load_json_config()

        # Note: If JSON config doesn't exist or fails to load,
        # class defaults will remain unchanged

    @staticmethod
    def _json_override(
        parser: configparser.ConfigParser, section: str, option: str, default
    ):
        if not parser.has_option(section, option):
            return default
        raw_value = parser.get(section, option)
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            loose = Config._loose_sequence_parse(raw_value, default)
            if loose is not None:
                return loose
            return default
        return parsed

    @staticmethod
    def _loose_sequence_parse(raw_value: str, default):
        if not isinstance(default, (list, tuple, set)):
            return None

        sample_items = list(default) if not isinstance(default, set) else list(default)
        if sample_items and not all(isinstance(item, str) for item in sample_items):
            return None

        stripped = raw_value.strip()
        if not (stripped.startswith("[") and stripped.endswith("]")):
            return None

        inner = stripped[1:-1]
        if not inner.strip():
            if isinstance(default, set):
                return set()
            if isinstance(default, tuple):
                return tuple()
            return []

        items: list[str] = []
        for part in inner.split(","):
            normalized = part.strip()
            if not normalized:
                continue

            if normalized[0] in {'"', "'"}:
                normalized = normalized[1:]
            if normalized and normalized[-1] in {'"', "'"}:
                normalized = normalized[:-1]

            normalized = normalized.strip()
            if normalized:
                items.append(normalized)

        if isinstance(default, set):
            return set(items)
        if isinstance(default, tuple):
            return tuple(items)
        return items

    @staticmethod
    def _tuple_list_override(
        parser: configparser.ConfigParser, section: str, option: str, default
    ):
        fallback = [list(item) for item in default]
        raw = Config._json_override(parser, section, option, fallback)
        return [tuple(item) for item in raw]

    @classmethod
    def _load_json_config(cls) -> bool:
        if not cls.CONFIG_JSON_FILE.exists():
            return False

        try:
            with cls.CONFIG_JSON_FILE.open("r", encoding="utf-8") as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False

        # Helper function to get nested value with fallback
        def get_nested(data, *keys, default=None):
            current = data
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current

        # Load general section
        cls.WELCOME_MESSAGE = get_nested(
            config_data, "general", "welcome_message", default=cls.WELCOME_MESSAGE
        )
        cls.SHOW_STARTUP_BANNER = get_nested(
            config_data,
            "general",
            "show_startup_banner",
            default=cls.SHOW_STARTUP_BANNER,
        )
        cls.REFRESH_RATE = get_nested(
            config_data, "general", "refresh_rate", default=cls.REFRESH_RATE
        )

        # Load shell section
        cls.MAX_SHELL_CONTEXT = get_nested(
            config_data, "shell", "max_shell_context", default=cls.MAX_SHELL_CONTEXT
        )

        interactive_commands = get_nested(
            config_data,
            "shell",
            "interactive_commands",
            default=list(cls.INTERACTIVE_COMMANDS),
        )
        if isinstance(interactive_commands, list):
            cls.INTERACTIVE_COMMANDS = set(interactive_commands)

        streaming_commands = get_nested(
            config_data,
            "shell",
            "streaming_commands",
            default=list(cls.STREAMING_COMMANDS),
        )
        if isinstance(streaming_commands, list):
            cls.STREAMING_COMMANDS = set(streaming_commands)

        cls.SHELL_STREAM_SUMMARY_PANEL = get_nested(
            config_data,
            "shell",
            "shell_stream_summary_panel",
            default=cls.SHELL_STREAM_SUMMARY_PANEL,
        )
        cls.SHELL_STREAM_OUTPUT_PANEL = get_nested(
            config_data,
            "shell",
            "shell_stream_output_panel",
            default=cls.SHELL_STREAM_OUTPUT_PANEL,
        )
        cls.CD_FEEDBACK_ENABLED = get_nested(
            config_data,
            "shell",
            "cd_feedback_enabled",
            default=cls.CD_FEEDBACK_ENABLED,
        )
        cls.DEFAULT_SHELL = get_nested(
            config_data, "shell", "default_shell", default=cls.DEFAULT_SHELL
        )
        cls.CHOICE_DEFAULT_SHELL = get_nested(
            config_data,
            "shell",
            "choice_default_shell",
            default=cls.CHOICE_DEFAULT_SHELL,
        )

        # Load UI section
        help_keybinds = get_nested(
            config_data,
            "ui",
            "help_keybinds",
            default=[list(item) for item in cls.HELP_KEYBINDS],
        )
        if isinstance(help_keybinds, list):
            cls.HELP_KEYBINDS = [tuple(item) for item in help_keybinds]

        help_special_commands = get_nested(
            config_data,
            "ui",
            "help_special_commands",
            default=[list(item) for item in cls.HELP_SPECIAL_COMMANDS],
        )
        if isinstance(help_special_commands, list):
            cls.HELP_SPECIAL_COMMANDS = [tuple(item) for item in help_special_commands]

        prompt_styles = get_nested(
            config_data, "ui", "prompt_styles", default=cls.PROMPT_STYLES
        )
        if isinstance(prompt_styles, dict):
            cls.PROMPT_STYLES.update(prompt_styles)

        completion_styles = get_nested(
            config_data, "ui", "completion_styles", default=cls.COMPLETION_STYLES
        )
        if isinstance(completion_styles, dict):
            cls.COMPLETION_STYLES.update(completion_styles)

        panel_styles = get_nested(
            config_data, "ui", "panel_styles", default=cls.PANEL_STYLES
        )
        if isinstance(panel_styles, dict):
            cls.PANEL_STYLES.update(panel_styles)

        cls.HIGHLIGHTER_ENABLED = get_nested(
            config_data, "ui", "highlighter_enabled", default=cls.HIGHLIGHTER_ENABLED
        )

        highlighter_rules = get_nested(
            config_data, "ui", "highlighter_rules", default=cls.HIGHLIGHTER_RULES
        )
        if isinstance(highlighter_rules, list):
            cls.HIGHLIGHTER_RULES = highlighter_rules

        highlighter_styles = get_nested(
            config_data, "ui", "highlighter_styles", default=cls.HIGHLIGHTER_STYLES
        )
        if isinstance(highlighter_styles, dict):
            cls.HIGHLIGHTER_STYLES.update(highlighter_styles)

        lexer_styles = get_nested(
            config_data, "ui", "lexer_styles", default=cls.LEXER_STYLES
        )
        if isinstance(lexer_styles, dict):
            cls.LEXER_STYLES.update(lexer_styles)

        command_highlight = get_nested(
            config_data, "ui", "command_highlight", default=cls.COMMAND_HIGHLIGHT
        )
        if isinstance(command_highlight, dict):
            cls.COMMAND_HIGHLIGHT.update(command_highlight)

        path_highlight = get_nested(
            config_data, "ui", "path_highlight", default=cls.PATH_HIGHLIGHT
        )
        if isinstance(path_highlight, dict):
            cls.PATH_HIGHLIGHT.update(path_highlight)

        cls.COMPLETION_AUTO_POPUP = get_nested(
            config_data,
            "ui",
            "completion_auto_popup",
            default=cls.COMPLETION_AUTO_POPUP,
        )
        cls.UI_REFRESH_INTERVAL_ENABLED = get_nested(
            config_data,
            "ui",
            "refresh_interval_enabled",
            default=cls.UI_REFRESH_INTERVAL_ENABLED,
        )
        cls.PROMPT_SYMBOL = get_nested(
            config_data, "ui", "prompt_symbol", default=cls.PROMPT_SYMBOL
        )
        cls.PROMPT_TEMPLATE_TOP = get_nested(
            config_data, "ui", "prompt_template_top", default=cls.PROMPT_TEMPLATE_TOP
        )
        cls.PROMPT_TEMPLATE_BOTTOM = get_nested(
            config_data,
            "ui",
            "prompt_template_bottom",
            default=cls.PROMPT_TEMPLATE_BOTTOM,
        )
        cls.PROMPT_PLACEHOLDER = get_nested(
            config_data, "ui", "prompt_placeholder", default=cls.PROMPT_PLACEHOLDER
        )
        cls.CHOICE_PROMPT_LEXER = get_nested(
            config_data, "ui", "choice_prompt_lexer", default=cls.CHOICE_PROMPT_LEXER
        )

        # Load syntax section
        syntax_extensions = get_nested(
            config_data, "syntax", "syntax_extensions", default=cls.SYNTAX_EXTENSIONS
        )
        if isinstance(syntax_extensions, dict):
            cls.SYNTAX_EXTENSIONS.update(syntax_extensions)

        syntax_highlight_commands = get_nested(
            config_data,
            "syntax",
            "syntax_highlight_commands",
            default=cls.SYNTAX_HIGHLIGHT_COMMANDS,
        )
        if isinstance(syntax_highlight_commands, list):
            cls.SYNTAX_HIGHLIGHT_COMMANDS = syntax_highlight_commands

        syntax_theme = get_nested(
            config_data,
            "syntax",
            "syntax_theme",
            default=cls.SYNTAX_THEME,
        )
        if isinstance(syntax_theme, str):
            cls.SYNTAX_THEME = syntax_theme

        ls_commands = get_nested(
            config_data, "syntax", "ls_commands", default=cls.LS_COMMANDS
        )
        if isinstance(ls_commands, list):
            cls.LS_COMMANDS = ls_commands

        file_icons = get_nested(
            config_data, "syntax", "file_icons", default=cls.FILE_ICONS
        )
        if isinstance(file_icons, dict):
            cls.FILE_ICONS.update(file_icons)

        file_colors = get_nested(
            config_data, "syntax", "file_colors", default=cls.FILE_COLORS
        )
        if isinstance(file_colors, dict):
            cls.FILE_COLORS.update(file_colors)

        file_extensions = get_nested(
            config_data, "syntax", "file_extensions", default=cls.FILE_EXTENSIONS
        )
        if isinstance(file_extensions, dict):
            cls.FILE_EXTENSIONS.update(file_extensions)

        bash_completion_files = get_nested(
            config_data,
            "syntax",
            "bash_completion_files",
            default=cls.BASH_COMPLETION_FILES,
        )
        if isinstance(bash_completion_files, list):
            cls.BASH_COMPLETION_FILES = bash_completion_files

        bash_completion_dirs = get_nested(
            config_data,
            "syntax",
            "bash_completion_dirs",
            default=cls.BASH_COMPLETION_DIRS,
        )
        if isinstance(bash_completion_dirs, list):
            cls.BASH_COMPLETION_DIRS = bash_completion_dirs

        fish_completion_dirs = get_nested(
            config_data,
            "syntax",
            "fish_completion_dirs",
            default=cls.FISH_COMPLETION_DIRS,
        )
        if isinstance(fish_completion_dirs, list):
            cls.FISH_COMPLETION_DIRS = fish_completion_dirs

        zsh_completion_dirs = get_nested(
            config_data,
            "syntax",
            "zsh_completion_dirs",
            default=cls.ZSH_COMPLETION_DIRS,
        )
        if isinstance(zsh_completion_dirs, list):
            cls.ZSH_COMPLETION_DIRS = zsh_completion_dirs

        nushell_completion_dirs = get_nested(
            config_data,
            "syntax",
            "nushell_completion_dirs",
            default=cls.NUSHELL_COMPLETION_DIRS,
        )
        if isinstance(nushell_completion_dirs, list):
            cls.NUSHELL_COMPLETION_DIRS = nushell_completion_dirs

        enabled_completion_shells = get_nested(
            config_data,
            "syntax",
            "enabled_completion_shells",
            default=cls.ENABLED_COMPLETION_SHELLS,
        )
        if isinstance(enabled_completion_shells, list):
            cls.ENABLED_COMPLETION_SHELLS = enabled_completion_shells

        completion_shell_order = get_nested(
            config_data,
            "syntax",
            "completion_shell_order",
            default=cls.COMPLETION_SHELL_ORDER,
        )
        if isinstance(completion_shell_order, list):
            cls.COMPLETION_SHELL_ORDER = completion_shell_order

        return True

    @classmethod
    def _convert_ini_to_json(cls) -> bool:
        if not cls.CONFIG_FILE.exists():
            return False

        # Load INI config using existing parser
        parser = configparser.ConfigParser()
        try:
            parser.read(cls.CONFIG_FILE, encoding="utf-8")
        except Exception:
            return False

        # Build JSON structure
        config_data = {}

        # Helper to parse JSON strings from INI
        def parse_ini_value(section, option, default):
            if not parser.has_option(section, option):
                return default

            value = parser.get(section, option)
            # Try to parse as JSON first
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # For simple strings/numbers/booleans
                if value.lower() in ("true", "false"):
                    return value.lower() == "true"
                try:
                    return int(value)
                except ValueError:
                    try:
                        return float(value)
                    except ValueError:
                        return value

        # Convert each section
        for section in parser.sections():
            config_data[section] = {}
            for option in parser.options(section):
                # Map INI option names to nested structure
                if section == "general":
                    config_data[section][option] = parse_ini_value(
                        section, option, getattr(cls, option.upper(), "")
                    )
                elif section == "shell":
                    config_data[section][option] = parse_ini_value(
                        section, option, getattr(cls, option.upper(), "")
                    )
                elif section == "ui":
                    config_data[section][option] = parse_ini_value(
                        section, option, getattr(cls, option.upper(), "")
                    )
                elif section == "syntax":
                    config_data[section][option] = parse_ini_value(
                        section, option, getattr(cls, option.upper(), "")
                    )

        # Write JSON file
        try:
            with cls.CONFIG_JSON_FILE.open("w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    @classmethod
    def _write_default_json_config(cls) -> None:
        config_data = {
            "general": {
                "welcome_message": cls.WELCOME_MESSAGE,
                "show_startup_banner": cls.SHOW_STARTUP_BANNER,
                "refresh_rate": cls.REFRESH_RATE,
            },
            "shell": {
                "max_shell_context": cls.MAX_SHELL_CONTEXT,
                "interactive_commands": sorted(cls.INTERACTIVE_COMMANDS),
                "streaming_commands": sorted(cls.STREAMING_COMMANDS),
                "shell_stream_summary_panel": cls.SHELL_STREAM_SUMMARY_PANEL,
                "shell_stream_output_panel": cls.SHELL_STREAM_OUTPUT_PANEL,
                "cd_feedback_enabled": cls.CD_FEEDBACK_ENABLED,
                "default_shell": cls.DEFAULT_SHELL,
                "choice_default_shell": cls.CHOICE_DEFAULT_SHELL,
            },
            "ui": {
                "help_keybinds": [list(item) for item in cls.HELP_KEYBINDS],
                "help_special_commands": [
                    list(item) for item in cls.HELP_SPECIAL_COMMANDS
                ],
                "prompt_styles": cls.PROMPT_STYLES,
                "completion_styles": cls.COMPLETION_STYLES,
                "panel_styles": cls.PANEL_STYLES,
                "highlighter_enabled": cls.HIGHLIGHTER_ENABLED,
                "highlighter_rules": cls.HIGHLIGHTER_RULES,
                "highlighter_styles": cls.HIGHLIGHTER_STYLES,
                "lexer_styles": cls.LEXER_STYLES,
                "command_highlight": cls.COMMAND_HIGHLIGHT,
                "path_highlight": cls.PATH_HIGHLIGHT,
                "completion_auto_popup": cls.COMPLETION_AUTO_POPUP,
                "refresh_interval_enabled": cls.UI_REFRESH_INTERVAL_ENABLED,
                "prompt_symbol": cls.PROMPT_SYMBOL,
                "prompt_template_top": cls.PROMPT_TEMPLATE_TOP,
                "prompt_template_bottom": cls.PROMPT_TEMPLATE_BOTTOM,
                "prompt_placeholder": cls.PROMPT_PLACEHOLDER,
                "choice_prompt_lexer": cls.CHOICE_PROMPT_LEXER,
            },
            "syntax": {
                "syntax_extensions": cls.SYNTAX_EXTENSIONS,
                "syntax_highlight_commands": cls.SYNTAX_HIGHLIGHT_COMMANDS,
                "syntax_theme": cls.SYNTAX_THEME,
                "ls_commands": cls.LS_COMMANDS,
                "file_icons": cls.FILE_ICONS,
                "file_colors": cls.FILE_COLORS,
                "file_extensions": cls.FILE_EXTENSIONS,
                "bash_completion_files": cls.BASH_COMPLETION_FILES,
                "bash_completion_dirs": cls.BASH_COMPLETION_DIRS,
                "fish_completion_dirs": cls.FISH_COMPLETION_DIRS,
                "zsh_completion_dirs": cls.ZSH_COMPLETION_DIRS,
                "nushell_completion_dirs": cls.NUSHELL_COMPLETION_DIRS,
                "enabled_completion_shells": cls.ENABLED_COMPLETION_SHELLS,
                "completion_shell_order": cls.COMPLETION_SHELL_ORDER,
            },
        }

        try:
            with cls.CONFIG_JSON_FILE.open("w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    @classmethod
    def _ensure_command_descriptions(cls) -> None:
        refresh_env = os.getenv("WRAPCLI_REFRESH_COMMANDS_DESC", "").strip().lower()
        refresh_requested = refresh_env in {"1", "true", "yes", "on"}
        if cls.COMMANDS_DESC_FILE.exists() and not refresh_requested:
            return
        cls._generate_command_descriptions()

    @classmethod
    def _generate_command_descriptions(cls) -> None:
        try:
            result = subprocess.run(
                ["apropos", "-s", "1,8", "."],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError:
            return
        except subprocess.SubprocessError:
            return

        if result.returncode != 0 or not result.stdout:
            return

        pattern = re.compile(r"^(\S+)\s+\(.*\)\s+-\s+(.*)")
        commands = {}

        for line in result.stdout.splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            command = match.group(1).strip()
            description = match.group(2).strip()
            if not command or len(command) >= 50:
                continue
            commands[command] = description

        if not commands:
            return

        try:
            cls.COMMANDS_DESC_FILE.write_text(
                json.dumps(commands, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    @classmethod
    def reload(cls) -> bool:
        try:
            cls.ensure_directories()
            cls._load_external_config()
            cls._ensure_command_descriptions()
            return True
        except Exception:
            return False


Config.ensure_directories()
Config._load_external_config()
