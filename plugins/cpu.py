#!/usr/bin/env python3
"""
CPU plugin for Simple-CLI
Shows current CPU usage in the prompt
"""

import time
import psutil

class CPUPlugin:
    """Plugin that shows CPU usage"""
    
    def __init__(self):
        self.name = "cpu_plugin"
        self.update_interval = 3.0
        self.last_update = 0.0
        self.cached_value = None
        self.enabled = True
    
    def should_update(self) -> bool:
        if not self.enabled:
            return False
        return time.time() - self.last_update >= self.update_interval
    
    def get_cached(self):
        return self.cached_value
    
    def update_cache(self, value):
        self.cached_value = value
        self.last_update = time.time()
    
    def execute(self):
        """Return CPU usage segment"""
        usage = int(psutil.cpu_percent())
        icon = ""
        yield {"values": {"cpu_plugin": f"{icon} {usage}%"}}

def create_plugin():
    """Plugin factory function"""
    return CPUPlugin()