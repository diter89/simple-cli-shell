#!/usr/bin/env python3
import os
import sys
import importlib
import importlib.util
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional, Iterable
from dataclasses import dataclass


@dataclass
class PluginMetadata:
    name: str
    version: str
    description: str
    author: str
    enabled: bool = True
    update_interval: float = 1.0
    dependencies: Optional[List[str]] = None


class BasePlugin(ABC):
    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self.last_update = 0
        self.cached_value = None
        self.enabled = metadata.enabled

    @abstractmethod
    def execute(self) -> Iterable[Any]:
        pass

    def should_update(self) -> bool:
        if not self.enabled:
            return False
        current_time = time.time()
        return current_time - self.last_update >= self.metadata.update_interval

    def get_cached_value(self):
        return self.cached_value

    def update_cache(self, value):
        self.cached_value = value
        self.last_update = time.time()


class PluginManager:
    def __init__(
        self, plugin_dirs: Optional[List[str]] = None, config_path: Optional[str] = None
    ):
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_dirs = plugin_dirs or self._get_default_plugin_dirs()
        self.config_path = config_path or self._get_default_config_path()
        self._load_plugin_config()
        self._discover_and_load_plugins()

    def _get_default_plugin_dirs(self) -> List[str]:
        home = Path.home()
        dirs = [str(home / ".simple_cli" / "plugins")]

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base_path = Path(sys.executable).parent
            dirs.append(str(base_path / "plugins"))
        else:
            dirs.append(str(Path(__file__).parent / "plugins"))

        dirs.append("/usr/local/share/simple-cli/plugins")
        return dirs

    def _get_default_config_path(self) -> str:
        return str(Path.home() / ".simple_cli" / "plugin_config.json")

    def _load_plugin_config(self):
        import json

        self.plugin_config = {}

        if not os.path.exists(self.config_path):
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load plugin config from {self.config_path}: {e}")
            return

        for key, value in config_data.items():
            if key == "plugins" and isinstance(value, dict):
                for plugin_name, plugin_config in value.items():
                    if isinstance(plugin_config, dict):
                        self.plugin_config[plugin_name] = plugin_config
            elif key.endswith("_plugin") and isinstance(value, dict):
                plugin_name = key.replace("_plugin", "")
                self.plugin_config[plugin_name] = value
            elif isinstance(value, dict) and "enabled" in value:
                self.plugin_config[key] = value

    def _discover_and_load_plugins(self):
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                continue

            self._load_plugins_from_directory(plugin_dir)

    def _load_plugins_from_directory(self, plugin_dir: str):
        for item in Path(plugin_dir).iterdir():
            if (
                item.is_file()
                and item.suffix == ".py"
                and not item.name.startswith("_")
            ):
                self._load_plugin_file(item)
            elif item.is_dir() and not item.name.startswith("_"):
                self._load_plugin_directory(item)

    def _load_plugin_file(self, plugin_file: Path):
        try:
            spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "create_plugin"):
                    plugin_instance = module.create_plugin()
                elif hasattr(module, "plugin"):
                    plugin_instance = module.plugin
                else:
                    return

                self.register_plugin(plugin_instance)
        except Exception as e:
            print(f"Error loading plugin {plugin_file}: {e}")

    def _load_plugin_directory(self, plugin_dir: Path):
        init_file = plugin_dir / "__init__.py"
        if init_file.exists():
            self._load_plugin_file(init_file)

    def register_plugin(self, plugin):
        if hasattr(plugin, "metadata"):
            plugin_name = plugin.metadata.name
            metadata = plugin.metadata
        else:
            plugin_name = getattr(plugin, "name", plugin.__class__.__name__.lower())
            metadata = PluginMetadata(
                name=plugin_name,
                version=getattr(plugin, "version", "1.0.0"),
                description=getattr(plugin, "description", "Legacy plugin"),
                author=getattr(plugin, "author", "Unknown"),
                enabled=getattr(plugin, "enabled", True),
                update_interval=getattr(plugin, "update_interval", 1.0),
                dependencies=None,
            )

            plugin.metadata = metadata

        if not self._check_plugin_dependencies(plugin):
            print(f"Plugin {plugin_name} dependencies not met, skipping")
            return

        if plugin_name in self.plugin_config:
            plugin.enabled = self.plugin_config[plugin_name].get("enabled", True)
            plugin.metadata.update_interval = self.plugin_config[plugin_name].get(
                "update_interval", plugin.metadata.update_interval
            )

        if not hasattr(plugin, "get_cached_value"):
            if hasattr(plugin, "get_cached"):
                plugin.get_cached_value = plugin.get_cached
            else:

                def get_cached_value_wrapper():
                    return getattr(plugin, "cached_value", None)

                plugin.get_cached_value = get_cached_value_wrapper

        if not hasattr(plugin, "update_cache"):

            def update_cache_wrapper(value):
                plugin.cached_value = value
                plugin.last_update = time.time()

            plugin.update_cache = update_cache_wrapper

        if not hasattr(plugin, "should_update"):

            def should_update_wrapper():
                if not getattr(plugin, "enabled", True):
                    return False
                current_time = time.time()
                return (
                    current_time - getattr(plugin, "last_update", 0)
                    >= plugin.metadata.update_interval
                )

            plugin.should_update = should_update_wrapper

        if not hasattr(plugin, "last_update"):
            plugin.last_update = 0
        if not hasattr(plugin, "cached_value"):
            plugin.cached_value = None

        if not hasattr(plugin, "enabled"):
            plugin.enabled = plugin.metadata.enabled

        self.plugins[plugin_name] = plugin

    def _check_plugin_dependencies(self, plugin: BasePlugin) -> bool:
        if not plugin.metadata.dependencies:
            return True

        for dep in plugin.metadata.dependencies:
            if dep not in self.plugins:
                return False
        return True

    def get_active_plugins(self) -> List[BasePlugin]:
        return [p for p in self.plugins.values() if p.enabled]

    def execute_plugins(self) -> List[Any]:
        results = []

        for plugin in self.get_active_plugins():
            if plugin.should_update():
                try:
                    plugin_output = list(plugin.execute())
                    plugin.update_cache(plugin_output)
                    results.extend(plugin_output)
                except Exception as e:
                    print(f"Error executing plugin {plugin.metadata.name}: {e}")

                    plugin.enabled = False
            else:
                cached = plugin.get_cached_value()
                if cached:
                    results.extend(cached)

        return results

    def enable_plugin(self, plugin_name: str):
        if plugin_name in self.plugins:
            self.plugins[plugin_name].enabled = True

    def disable_plugin(self, plugin_name: str):
        if plugin_name in self.plugins:
            self.plugins[plugin_name].enabled = False

    def get_plugin_info(self) -> Dict[str, Dict[str, Any]]:
        info = {}
        for name, plugin in self.plugins.items():
            info[name] = {
                "version": plugin.metadata.version,
                "description": plugin.metadata.description,
                "author": plugin.metadata.author,
                "enabled": plugin.enabled,
                "update_interval": plugin.metadata.update_interval,
                "dependencies": plugin.metadata.dependencies or [],
                "last_update": plugin.last_update,
            }
        return info

    def reload_plugins(self):
        self.plugins.clear()
        self._discover_and_load_plugins()


_plugin_manager = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def register_plugin(plugin: BasePlugin):
    get_plugin_manager().register_plugin(plugin)


def get_plugin_output() -> List[Any]:
    return get_plugin_manager().execute_plugins()


def plugin(metadata: PluginMetadata):
    def decorator(cls):
        if not issubclass(cls, BasePlugin):
            raise TypeError("Plugin must inherit from BasePlugin")

        instance = cls(metadata)
        register_plugin(instance)
        return cls

    return decorator
