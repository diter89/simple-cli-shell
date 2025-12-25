#!/usr/bin/env python3


import time
from datetime import datetime
from typing import Iterable, Any


class BatteryPlugin:
    def __init__(self):
        self.name = "battery"
        self.version = "1.0.0"
        self.description = "Shows animated battery icon"
        self.author = "Simple-CLI"
        self.update_interval = 2.0
        self.last_update = 0
        self.cached_value = None
        self.enabled = True
    def should_update(self):
        current_time = time.time()
        return current_time - self.last_update >= self.update_interval
    def get_cached_value(self):
        return self.cached_value
    def update_cache(self, value):
        self.cached_value = value
        self.last_update = time.time()
    def execute(self):
        icons = [
            "",  # 0%
            "",  # 25%
            "",  # 50%
            "",  # 75%
            "",  # 100%
        ]
        now = datetime.now()
        frame = (now.second // 2) % len(icons)
        icon = icons[frame]
        yield {"values": {"battery_plugin": icon}}


def create_plugin():
    return BatteryPlugin()