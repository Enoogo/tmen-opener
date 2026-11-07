"""TMEN Opener —— 泰盟 BL 系列 .tmen 波形查看器。

用法::

    python main.py                  # 打开空窗口，再拖入/选择 .tmen 文件
    python main.py a.tmen b.tmen    # 直接以标签页打开多个文件
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许从任意工作目录运行（双击 py / exe 时尤其重要）
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("TkAgg")

import tkinter as tk
from tkinter import messagebox

from tmen.config import Config
from tmen.style import init_matplotlib
from tmen.ui import HAS_DND, App

if HAS_DND:
    from tkinterdnd2 import TkinterDnD


def _enable_hidpi() -> None:
    """Windows 高 DPI 下避免界面模糊。"""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _enable_hidpi()

    cfg = Config.load()
    init_matplotlib(cfg.font_list())

    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    try:
        app = App(root, cfg)
    except Exception as exc:  # 兜底：避免闪退后什么都看不到
        messagebox.showerror("启动失败", str(exc))
        raise

    files = [a for a in argv if not a.startswith("-")]
    if files:
        root.after(60, lambda: [app.open_file(f) for f in files])
    else:
        root.after(120, app.open_dialog if cfg.get("app.auto_open_dialog", False) else (lambda: None))

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
