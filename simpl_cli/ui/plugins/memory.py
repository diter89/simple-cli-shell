#!/usr/bin/env python3


import time
import psutil
from typing import Iterable, Any


class MemoryPlugin:
    def __init__(self):
        self.name = "memory"
        self.version = "1.0.0"
        self.description = "Shows current memory usage"
        self.author = "Simple-CLI"
        self.update_interval = 5.0
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
        mem = psutil.virtual_memory()
        usage = int(mem.used / 1024**3)
        total = int(mem.total / 1024**3)
        yield {"values": {"memory_plugin": f"󰍛 {usage}G/{total}G"}}


def create_plugin():
    return MemoryPlugin()