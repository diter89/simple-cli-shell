#!/usr/bin/env python3


import time
import psutil
from typing import Iterable, Any


class CPUPlugin:
    def __init__(self):
        self.name = "cpu"
        self.version = "1.0.0"
        self.description = "Shows current CPU usage"
        self.author = "Simple-CLI"
        self.update_interval = 3.0
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
        usage = int(psutil.cpu_percent())
        icon = ""
        yield {"values": {"cpu_plugin": f"{icon} {usage}%"}}


def create_plugin():
    return CPUPlugin()