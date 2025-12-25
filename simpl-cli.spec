# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

# Collect all submodules from simpl_cli
simpl_cli_hiddenimports = collect_submodules('simpl_cli')

a = Analysis(
    ['simpl_cli/cli.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'simpl_cli',
        'simpl_cli.ui.plugin_system',
        'simpl_cli.ui.simple_plugins',
        'rich',
        'prompt_toolkit',
        'pyperclip',
        'psutil',
        'sqlite3',
    ] + simpl_cli_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='simpl-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
