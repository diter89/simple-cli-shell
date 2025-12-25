#!/usr/bin/env python3

import sys
from prompt_toolkit import prompt

from .config import Config
from .core import HybridShell
from .ui.highlighter import create_console


def check_dependencies() -> None:
    try:
        import rich
        import prompt_toolkit
        import psutil
    except ImportError as error:
        print(f" Required dependency not found: {error}")
        print("Please install required packages:")
        print("pip install rich prompt-toolkit psutil")

        try:
            import tomli
        except ImportError:
            print("Optional: pip install tomli (for Poetry project detection)")

        sys.exit(1)


def main() -> None:
    check_dependencies()
    Config.ensure_directories()

    shell = HybridShell()
    shell.run()


if __name__ == "__main__":
    main()
