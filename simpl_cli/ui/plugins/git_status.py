#!/usr/bin/env python3


import time
import subprocess
from typing import Iterable, Any


class GitStatusPlugin:
    def __init__(self):
        self.name = "git_status"
        self.version = "1.0.0"
        self.description = "Shows git repository status"
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
        try:
            output = subprocess.check_output(
                ["git", "status", "--porcelain"],
                stderr=subprocess.STDOUT
            ).decode().splitlines()

            staged = sum(1 for x in output if x.startswith("M "))
            modified = sum(1 for x in output if x.startswith(" M"))
            untracked = sum(1 for x in output if x.startswith("??"))

            icon = f"󰛿 {modified} 󰙴 {staged} 󰘓 {untracked}"
        except:
            icon = ""

        yield {"values": {"git_status_plugin": icon}}


def create_plugin():
    return GitStatusPlugin()