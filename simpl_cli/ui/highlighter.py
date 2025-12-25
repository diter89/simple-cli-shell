#!/usr/bin/env python3
import re
from typing import List, Tuple

from rich.console import Console
from rich.highlighter import Highlighter

from ..config import Config


class ConfigurableHighlighter(Highlighter):
    def __init__(self, rules: List[dict]) -> None:
        super().__init__()
        self._patterns: List[Tuple[re.Pattern[str], str]] = []

        for rule in rules or []:
            pattern = rule.get("pattern")
            style = rule.get("style")
            if not pattern or not style:
                continue

            style_value = Config.HIGHLIGHTER_STYLES.get(style, style)
            if not style_value:
                continue

            flags = re.MULTILINE
            if rule.get("ignore_case"):
                flags |= re.IGNORECASE

            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue

            self._patterns.append((compiled, style_value))

    def highlight(self, text) -> None:
        if not self._patterns:
            return

        plain = text.plain
        for regex, style in self._patterns:
            for match in regex.finditer(plain):
                start, end = match.span()
                if start == end:
                    continue
                text.stylize(style, start, end)


def create_console() -> Console:
    highlighter = None
    if Config.is_highlighter_enabled() and Config.HIGHLIGHTER_RULES:
        highlighter = ConfigurableHighlighter(Config.HIGHLIGHTER_RULES)

    if highlighter:
        return Console(highlighter=highlighter)

    return Console()
