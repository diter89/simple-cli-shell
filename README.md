# Simple-cli-shell

**Simple-cli-shell** is an enhanced shell wrapper with rich UI, multi-shell completion, and environment detection.

Experimental / Toy Project | **License:** MIT (use/modify freely, no restrictions)  
**As-is:** No warranty, no support

## Installation

```bash
pip install .
```



## Key Bindings

| Key | Action |
|-----|--------|
| `Alt+H` | Help |
| `Alt+C` | Clear |
| `Ctrl+C` | Exit |

## Shell Completion Support

Simple-CLI supports multiple shell completion systems:

### Available Completion Systems
- **Bash**: Default completion system (already supported)
- **Fish**: Rich completion with descriptions
- **Zsh**: Advanced completion system  
- **Nushell**: Modern shell completion

### Configuration
Edit `~/.simple_cli/config.json` to customize completion:

```json
{
  "syntax": {
    "enabled_completion_shells": ["fish", "zsh", "bash", "nushell"],
    "completion_shell_order": ["fish", "zsh", "bash", "nushell"],
    "fish_completion_dirs": [
      "~/.config/fish/completions",
      "/usr/share/fish/completions"
    ],
    "zsh_completion_dirs": [
      "~/.zsh/completions",
      "/usr/share/zsh/functions/Completion"
    ],
    "nushell_completion_dirs": [
      "~/.config/nushell/completions"
    ]
  }
}
```

### How It Works
1. Simple-CLI tries each enabled shell in the specified order
2. First shell that returns completions wins
3. Fish completions include descriptions (if available)
4. Falls back to bash completion if others fail

## Structure

```
.
├── __init__.py
├── app.py              # Main application setup and initialization
├── cli.py              # Entry point for the command-line interface (CLI)
├── commands
│   ├── __init__.py
│   └── executor.py     # Handles execution of shell commands (ls, cd, etc.)
├── completion.py       # Manages command and path auto-completion
├── config.py           # Central configuration for the entire application
├── core
│   ├── __init__.py
│   ├── hybrid_shell.py # The main orchestrator for shell mode
│   └── script_runtime.py # Handles script execution and runtime
├── customization.py    # Simple API for customizing the shell's components
├── environment.py      # Detects the user's environment (Git, Python, etc.)
└── ui
    ├── __init__.py
    ├── highlighter.py  # Provides custom syntax highlighting
    ├── manager.py      # Manages static UI elements (prompts, panels, tables)
    ├── streaming.py    # Manages live, streaming display of shell output
    ├── theme.py        # Defines the visual theme (colors, styles) for UI panels
    ├── plugin_system.py # Plugin system for UI extensions
    └── plugins
        ├── __init__.py
        ├── cpu.py      # CPU usage plugin
        ├── battery.py  # Battery status plugin
        ├── clock.py    # Clock plugin
        ├── git_status.py # Git status plugin
        └── memory.py   # Memory usage plugin
```

## Screenshots
