#!/usr/bin/env python3
"""
Git Status Plugin for Simple-CLI
"""

import subprocess
import os
import time
from pathlib import Path

class GitStatusPlugin:
    def __init__(self):
        self.name = "git_status"
        self.enabled = True
        self.last_update = 0
        self.cached_value = None
        self.update_interval = 5.0  # seconds
    
    def should_update(self):
        """Check if plugin should update based on interval"""
        if not self.enabled:
            return False
        current_time = time.time()
        return current_time - self.last_update >= self.update_interval
    
    def get_cached_value(self):
        """Get cached plugin output"""
        return self.cached_value
    
    def update_cache(self, value):
        """Update cache with new value"""
        self.cached_value = value
        self.last_update = time.time()
    
    def execute(self):
        """Execute git status plugin"""
        try:
            # Get current directory
            current_dir = os.getcwd()
            
            # Check if we're in a git repository
            git_dir = subprocess.check_output(
                ['git', 'rev-parse', '--git-dir'],
                stderr=subprocess.PIPE,
                text=True
            ).strip()
            
            # Get current branch
            try:
                branch = subprocess.check_output(
                    ['git', 'branch', '--show-current'],
                    stderr=subprocess.PIPE,
                    text=True
                ).strip()
            except subprocess.CalledProcessError:
                # Fall back to different method for older git versions
                try:
                    branch = subprocess.check_output(
                        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                        stderr=subprocess.PIPE,
                        text=True
                    ).strip()
                except subprocess.CalledProcessError:
                    branch = "unknown"
            
            # Check for uncommitted changes
            try:
                status_output = subprocess.check_output(
                    ['git', 'status', '--porcelain'],
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                lines = status_output.strip().split('\n') if status_output.strip() else []
                has_changes = len(lines) > 0 and lines[0] != ''
                
                if has_changes:
                    # Count different types of changes
                    unstaged = []
                    staged = []
                    untracked = []
                    
                    for line in lines:
                        if len(line) >= 2:
                            if line[0] == '?' and line[1] == '?':
                                untracked.append(line[3:])
                            elif line[0] == ' ' and line[1] != ' ':
                                unstaged.append(line[3:])
                            elif line[0] != ' ' and line[1] == ' ':
                                staged.append(line[2:])
                            elif line[0] != ' ' and line[1] != ' ':
                                # Changed and staged
                                staged.append(line[2:])
                    
                    # Create status indicator
                    dirty_indicator = "≠"
                    if untracked:
                        dirty_indicator += "+"
                    if unstaged:
                        dirty_indicator += "~"
                    if staged:
                        dirty_indicator += "!"
                    
                    status_text = f" {branch} {dirty_indicator}"
                else:
                    status_text = f" {branch} "
                
            except subprocess.CalledProcessError:
                status_text = f" {branch} "
            
            result = [{"values": {"git_status_plugin": status_text}}]
            self.update_cache(result)
            return result
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Not in a git repository
            result = []
            self.update_cache(result)
            return result

def create_plugin():
    return GitStatusPlugin()

# For direct testing
if __name__ == "__main__":
    plugin = create_plugin()
    result = list(plugin.execute())
    print(result)