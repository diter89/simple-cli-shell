#!/usr/bin/env python3
"""
Clock plugin for Simple-CLI
Shows current time in the prompt
"""

import time
from datetime import datetime

class ClockPlugin:
    """Plugin that shows current time"""
    
    def __init__(self):
        self.name = "clock_plugin"
        self.update_interval = 1.0
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
        """Return clock segment"""
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        yield {"values": {"clock_plugin": time_str}}

def create_plugin():
    """Plugin factory function"""
    return ClockPlugin()