#!/usr/bin/env python3
"""
Memory Usage Plugin for Simple-CLI
"""

import psutil

class MemoryPlugin:
    def __init__(self):
        self.name = "memory"
    
    def execute(self):
        """Execute memory usage plugin"""
        try:
            # Get memory information
            memory = psutil.virtual_memory()
            
            # Calculate percentage
            percent = memory.percent
            
            # Get total and used memory in GB
            total_gb = memory.total / (1024**3)
            used_gb = memory.used / (1024**3)
            available_gb = memory.available / (1024**3)
            
            # Create memory icon based on usage
            if percent >= 90:
                icon = "󰍛"  # Full memory
                style = "high"
            elif percent >= 70:
                icon = "󰍚"  # Medium-high
                style = "medium"
            elif percent >= 40:
                icon = "󰍙"  # Medium
                style = "medium"
            else:
                icon = "󰍘"  # Low
                style = "low"
            
            # Format display text
            if total_gb < 1:
                # Show in MB for small memory systems
                total_mb = memory.total / (1024**2)
                used_mb = memory.used / (1024**2)
                memory_text = f"{icon} {percent}% ({used_mb:.0f}MB/{total_mb:.0f}MB)"
            else:
                # Show in GB for larger systems
                memory_text = f"{icon} {percent}% ({used_gb:.1f}GB/{total_gb:.1f}GB)"
            
            yield {"values": {"memory_plugin": memory_text}}
            
        except Exception:
            # Fallback in case of errors
            yield {}

def create_plugin():
    return MemoryPlugin()

# For direct testing
if __name__ == "__main__":
    plugin = create_plugin()
    result = list(plugin.execute())
    print(result)