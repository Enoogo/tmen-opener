# tmen-opener.spec — PyInstaller 打包配置
#   pyinstaller tmen-opener.spec
# 产物：dist/tmen-opener-2.1.0.exe
# 注意：config.json 会随包分发，运行时优先读写 exe 同目录下的 config.json。
# -*- mode: python ; coding: utf-8 -*-
import sysconfig

from PyInstaller.utils.hooks import collect_data_files

MAIN_SCRIPT = "main.py"
APP_NAME = "tmen-opener-2.1.0"

hidden = ["matplotlib.backends.backend_tkagg", "tkinterdnd2"]
data_files = [("config.json", ".")]
tkdnd_platform = {
    "win32": "win-x86", "win-amd64": "win-x64", "win-arm64": "win-arm64",
}.get(sysconfig.get_platform())
if tkdnd_platform:
    data_files += collect_data_files("tkinterdnd2", includes=[f"tkdnd/{tkdnd_platform}*/**"])

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[],
    binaries=[],
    datas=data_files,
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
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
