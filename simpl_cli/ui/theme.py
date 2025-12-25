#!/usr/bin/env python3
from dataclasses import dataclass
from typing import Any, Dict, Optional
from rich.panel import Panel
from rich.text import Text
from ..config import Config


@dataclass(frozen=True)
class PanelStyle:
    border_style: str
    padding: Optional[tuple[int, int]] = (0, 1)
    title_style: Optional[str] = None
    title_align: str = "left"
    subtitle_style: Optional[str] = None
    background_style: Optional[str] = None
    expand: bool = False


class PanelTheme:
    @staticmethod
    def get_style(name: str) -> PanelStyle:
        theme = Config.PANEL_STYLES.get(name, Config.PANEL_STYLES["default"])
        default_theme = Config.PANEL_STYLES["default"]

        border_style = theme.get(
            "border_style", default_theme.get("border_style", "#888888")
        )
        padding = theme.get("padding", default_theme.get("padding"))
        title_style = theme.get("title_style")
        title_align = theme.get("title_align", default_theme.get("title_align", "left"))
        subtitle_style = theme.get("subtitle_style")
        background_style = theme.get("background_style")
        expand = theme.get("expand", default_theme.get("expand", False))

        return PanelStyle(
            border_style=border_style,
            padding=padding,
            title_style=title_style,
            title_align=title_align,
            subtitle_style=subtitle_style,
            background_style=background_style,
            expand=expand,
        )

    @staticmethod
    def build(
        renderable: Any,
        title: str | Text = "",
        style: str = "default",
        *,
        fit: bool = False,
        **overrides: Any,
    ) -> Panel:
        panel_style = PanelTheme.get_style(style)

        panel_kwargs: Dict[str, Any] = {"border_style": panel_style.border_style}
        if panel_style.padding is not None:
            panel_kwargs["padding"] = panel_style.padding
        if panel_style.title_align:
            panel_kwargs["title_align"] = panel_style.title_align
        if panel_style.subtitle_style:
            panel_kwargs["subtitle_style"] = panel_style.subtitle_style
        if panel_style.background_style:
            panel_kwargs["style"] = panel_style.background_style
        if panel_style.expand:
            panel_kwargs["expand"] = panel_style.expand

        panel_kwargs.update(overrides)

        title_value = title
        if isinstance(title, str) and panel_style.title_style:
            title_value = Text(title, style=panel_style.title_style)

        if fit:
            return Panel.fit(renderable, title=title_value, **panel_kwargs)

        return Panel(renderable, title=title_value, **panel_kwargs)
