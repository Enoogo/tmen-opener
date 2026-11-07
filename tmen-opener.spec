# tmen-opener.spec — PyInstaller 打包配置
#   pyinstaller tmen-opener.spec
# 产物：dist/TMEN_Viewer(.exe)
# 注意：config.json 会随包分发，运行时优先读写 exe 同目录下的 config.json。
# -*- mode: python ; coding: utf-8 -*-
import os

MAIN_SCRIPT = "main.py"
APP_NAME = "TMEN_Viewer"

hidden = ["matplotlib.backends.backend_tkagg", "tkinterdnd2"]

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[],
    binaries=[],
    datas=[("config.json", ".")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest", "IPython", "jedi", "parso", "pandas", "scipy",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
        "pydoc_data", "test",
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_webagg",
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll", "vcruntime140_1.dll",
        "python311.dll", "tcl86t.dll", "tk86t.dll",
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
