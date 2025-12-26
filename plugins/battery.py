#!/usr/bin/env python3
"""
Battery Status Plugin for Simple-CLI
"""

import os
import subprocess
import re

class BatteryPlugin:
    def __init__(self):
        self.name = "battery"
    
    def execute(self):
        """Execute battery status plugin"""
        try:
            # Try to get battery information from /sys/class/power_supply/
            battery_info = self._get_battery_info_sysfs()
            
            if battery_info:
                percentage = battery_info.get("percentage", 0)
                status = battery_info.get("status", "Unknown")
                
                # Create battery icon based on percentage and status
                if status == "Charging":
                    icon = "󰂄"
                elif status == "Full":
                    icon = "󰁹"
                elif percentage >= 90:
                    icon = "󰁹"
                elif percentage >= 70:
                    icon = "󰂀"
                elif percentage >= 50:
                    icon = "󰁿"
                elif percentage >= 30:
                    icon = "󰁾"
                elif percentage >= 10:
                    icon = "󰁽"
                else:
                    icon = "󰂎"  # Critical
                
                battery_text = f"{icon} {percentage}%"
                yield {"values": {"battery_plugin": battery_text}}
            else:
                # Try acpi command as fallback
                battery_info = self._get_battery_info_acpi()
                if battery_info:
                    battery_text = battery_info.get("text", "󰁹 100%")
                    yield {"values": {"battery_plugin": battery_text}}
                else:
                    # No battery information available
                    yield {}
                    
        except Exception:
            # Error getting battery information
            yield {}
    
    def _get_battery_info_sysfs(self):
        """Get battery information from /sys/class/power_supply/"""
        battery_path = "/sys/class/power_supply"
        
        try:
            # Find battery directory (BAT0, BAT1, etc.)
            battery_dirs = [d for d in os.listdir(battery_path) if d.startswith("BAT")]
            if not battery_dirs:
                return None
            
            bat_dir = os.path.join(battery_path, battery_dirs[0])
            
            # Read capacity
            capacity_file = os.path.join(bat_dir, "capacity")
            if os.path.exists(capacity_file):
                with open(capacity_file, 'r') as f:
                    percentage = int(f.read().strip())
            else:
                # Try energy_full and energy_now
                energy_full_file = os.path.join(bat_dir, "energy_full")
                energy_now_file = os.path.join(bat_dir, "energy_now")
                
                if os.path.exists(energy_full_file) and os.path.exists(energy_now_file):
                    with open(energy_full_file, 'r') as f:
                        energy_full = int(f.read().strip())
                    with open(energy_now_file, 'r') as f:
                        energy_now = int(f.read().strip())
                    
                    percentage = int((energy_now / energy_full) * 100) if energy_full > 0 else 0
                else:
                    return None
            
            # Read status
            status_file = os.path.join(bat_dir, "status")
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    status = f.read().strip()
            else:
                status = "Unknown"
            
            return {
                "percentage": percentage,
                "status": status
            }
            
        except (OSError, ValueError, IndexError):
            return None
    
    def _get_battery_info_acpi(self):
        """Get battery information using acpi command"""
        try:
            result = subprocess.run(
                ["acpi", "-b"],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                output = result.stdout
                
                # Parse acpi output
                # Example: "Battery 0: Discharging, 87%, 02:45:32 remaining"
                match = re.search(r'Battery \d+:\s*(\w+),\s*(\d+)%', output)
                if match:
                    status = match.group(1)
                    percentage = int(match.group(2))
                    
                    # Create icon
                    if status.lower() == "charging":
                        icon = "󰂄"
                    elif status.lower() == "full":
                        icon = "󰁹"
                    elif percentage >= 90:
                        icon = "󰁹"
                    elif percentage >= 70:
                        icon = "󰂀"
                    elif percentage >= 50:
                        icon = "󰁿"
                    elif percentage >= 30:
                        icon = "󰁾"
                    elif percentage >= 10:
                        icon = "󰁽"
                    else:
                        icon = "󰂎"
                    
                    return {
                        "text": f"{icon} {percentage}%",
                        "percentage": percentage,
                        "status": status
                    }
        
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        return None

def create_plugin():
    return BatteryPlugin()

# For direct testing
if __name__ == "__main__":
    plugin = create_plugin()
    result = list(plugin.execute())
    print(result)