#!/usr/bin/env python3


import time
from datetime import datetime
from typing import Iterable, Any


class BasePlugin:
    pass


class PluginMetadata:
    pass


class ClockPlugin(BasePlugin):
    def __init__(self):
        self.name = "clock"
        self.version = "1.0.0"
        self.description = "Shows current time in prompt"
        self.author = "Simple-CLI"
        self.update_interval = 1.0
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
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        yield {"values": {"clock_plugin": time_str}}


def create_plugin():
    return ClockPlugin()