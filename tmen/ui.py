"""主窗口：工具栏 + 多标签页 + 状态栏。"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .config import Config
from .dialogs import ToolkitWindow
from .parser import TmenData, read_tmen
from .plot import PlotPage

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:  # pragma: no cover - 可选依赖
    DND_FILES = None
    TkinterDnD = None
    HAS_DND = False


BG_BAR = "#F7F8FA"
BG_TAB = "#E9EBEF"
BG_TAB_ACTIVE = "#FFFFFF"
FG_TAB = "#5A6068"
FG_TAB_ACTIVE = "#1858B8"
ACCENT = "#1858B8"


# --------------------------------------------------------------------------- #
# 标签栏
# --------------------------------------------------------------------------- #
class _Tab:
    __slots__ = ("key", "frame", "label", "close", "accent")

    def __init__(self, key: str, frame: tk.Frame, label: tk.Label,
                 close: tk.Label, accent: tk.Frame) -> None:
        self.key = key
        self.frame = frame
        self.label = label
        self.close = close
        self.accent = accent


class TabBar(tk.Frame):
    """可点击、可关闭、可拖动排序的标签栏（不依赖 ttk.Notebook）。"""

    def __init__(self, master, on_select, on_close, on_new=None) -> None:
        super().__init__(master, bg=BG_BAR, height=30)
        self.on_select = on_select
        self.on_close = on_close
        self.on_new = on_new or on_select
        self.tabs: Dict[str, _Tab] = {}
        self.order: List[str] = []
        self.current_key: Optional[str] = None
        self._drag: Optional[dict] = None

        self.holder = tk.Frame(self, bg=BG_BAR)
        self.holder.pack(side="left", fill="y")

        self.plus = tk.Label(
            self.holder, text=" ＋ ", bg=BG_BAR, fg="#1858B8",
            font=("Segoe UI", 13, "bold"), cursor="hand2",
        )
        self.plus.pack(side="left", padx=(2, 0), pady=2)
        self.plus.bind("<Button-1>", lambda e: self.on_new())

    # ---------------- 增删 ----------------
    def add(self, key: str, title: str) -> None:
        frame = tk.Frame(self.holder, bg=BG_TAB, cursor="hand2")
        frame.pack(side="left", padx=(3, 0), pady=(3, 0))

        label = tk.Label(
            frame, text=title, bg=BG_TAB, fg=FG_TAB, padx=9, pady=3,
            font=("Microsoft YaHei UI", 9), cursor="hand2", anchor="w",
        )
        label.pack(side="left")
        close = tk.Label(
            frame, text="✕", bg=BG_TAB, fg="#8A9099", padx=6,
            font=("Segoe UI", 8), cursor="hand2",
        )
        close.pack(side="left")
        accent = tk.Frame(frame, bg=BG_TAB, height=2)
        accent.pack(side="bottom", fill="x")

        tab = _Tab(key, frame, label, close, accent)
        self.tabs[key] = tab
        self.order.append(key)

        for widget in (frame, label):
            widget.bind("<Button-1>", lambda e, k=key: self._on_press(e, k))
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)
        close.bind("<Button-1>", lambda e, k=key: self._close(k))
        close.bind("<Enter>", lambda e, w=close: w.configure(fg="#D0021B"))
        close.bind("<Leave>", lambda e, w=close: w.configure(fg="#8A9099"))

        self.select(key)

    def remove(self, key: str) -> None:
        tab = self.tabs.pop(key, None)
        if tab is None:
            return
        tab.frame.destroy()
        if key in self.order:
            self.order.remove(key)
        if self.current_key == key:
            self.current_key = None
            if self.order:
                self.select(self.order[-1])
            else:
                self.on_select(None)

    def set_title(self, key: str, title: str) -> None:
        tab = self.tabs.get(key)
        if tab is None:
            return
        text = title if len(title) <= 28 else title[:27] + "…"
        tab.label.configure(text=text)

    def select(self, key: str) -> None:
        self.current_key = key
        for k, tab in self.tabs.items():
            active = k == key
            bg = BG_TAB_ACTIVE if active else BG_TAB
            tab.frame.configure(bg=bg)
            tab.label.configure(bg=bg, fg=FG_TAB_ACTIVE if active else FG_TAB,
                                font=("Microsoft YaHei UI", 9, "bold" if active else "normal"))
            tab.close.configure(bg=bg)
            tab.accent.configure(bg=ACCENT if active else bg)
        self.on_select(key)

    def count(self) -> int:
        return len(self.order)

    # ---------------- 拖动排序 ----------------
    def _on_press(self, event, key: str) -> None:
        tab = self.tabs[key]
        self._drag = {"key": key, "start_x": event.x_root,
                      "moved": False, "width": tab.frame.winfo_width()}
        self.select(key)

    def _on_drag(self, event) -> None:
        if not self._drag:
            return
        if abs(event.x_root - self._drag["start_x"]) < 8:
            return
        self._drag["moved"] = True
        key = self._drag["key"]
        target = self._index_at(event.x_root)
        if target is None:
            return
        cur = self.order.index(key)
        if target != cur:
            self.order.pop(cur)
            self.order.insert(target, key)
            self._repack()

    def _on_release(self, _event) -> None:
        self._drag = None

    def _index_at(self, x_root: int) -> Optional[int]:
        for index, key in enumerate(self.order):
            tab = self.tabs[key]
            x0 = tab.frame.winfo_rootx()
            w = tab.frame.winfo_width()
            if x_root < x0 + w / 2:
                return index
        return len(self.order) - 1 if self.order else None

    def _repack(self) -> None:
        for key in self.order:
            tab = self.tabs[key]
            tab.frame.pack_forget()
        for key in self.order:
            self.tabs[key].frame.pack(side="left", padx=(3, 0), pady=(3, 0))
        self.plus.pack_forget()
        self.plus.pack(side="left", padx=(2, 0), pady=2)

    def _close(self, key: str) -> None:
        self.on_close(key)


# --------------------------------------------------------------------------- #
# 主应用
# --------------------------------------------------------------------------- #
class App:
    """把工具栏、标签页、状态栏和配置串起来。"""

    def __init__(self, root, cfg: Config) -> None:
        self.root = root
        self.cfg = cfg
        self.pages: Dict[str, PlotPage] = {}
        self._seq = 0
        self.toolkit: Optional[ToolkitWindow] = None

        root.title(str(cfg.get("app.title", "泰盟 BL .tmen 波形查看器")))
        root.geometry(f"{cfg.get('app.window_width', 1280)}x{cfg.get('app.window_height', 800)}")
        root.minsize(900, 560)
        root.configure(bg=BG_BAR)

        self._build_toolbar()
        self.tabs = TabBar(root, self._on_tab_select, self._on_tab_close,
                           on_new=self.open_dialog)
        self.tabs.pack(side="top", fill="x")

        self.status = tk.Label(
            root, text="就绪 — 拖入 .tmen 文件，或点击左上角“打开文件”",
            anchor="w", bg="#E9EBEF", fg="#404040", padx=10, pady=3,
            font=("Microsoft YaHei UI", 9),
        )
        self.status.pack(side="bottom", fill="x")

        self.content = tk.Frame(root, bg="#FFFFFF")
        self.content.pack(side="top", fill="both", expand=True)

        self._placeholder = tk.Label(
            self.content,
            text="\n\n把 .tmen 文件拖到这里，或点击“打开文件”\n\n"
                 "左键拖动=平移　右键拖动=框选缩放　滚轮=横轴缩放　Ctrl+滚轮=纵轴缩放",
            bg="#FFFFFF", fg="#9AA0A6", font=("Microsoft YaHei UI", 11),
            justify="center",
        )
        self._placeholder.pack(expand=True)

        self._bind_shortcuts()
        self._bind_dnd()

    # ---------------- 工具栏 ----------------
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=BG_BAR, height=38)
        bar.pack(side="top", fill="x")
        self.toolbar = bar

        def button(text, command, width=None, tip=""):
            b = tk.Button(
                bar, text=text, command=command, relief="flat",
                bg="#FFFFFF", fg="#333333", activebackground="#E8F0FB",
                activeforeground=ACCENT, bd=1, padx=10, pady=3,
                font=("Microsoft YaHei UI", 9), cursor="hand2",
                highlightthickness=1, highlightbackground="#D5D9DE",
            )
            if width:
                b.configure(width=width)
            b.pack(side="left", padx=(6, 0), pady=6)
            if tip:
                _Tooltip(b, tip)
            return b

        button("打开文件", self.open_dialog, tip="Ctrl+O")
        button("重新载入", self.reload_current, tip="按当前配置重新解析文件")
        button("保存图片", self.save_image, tip="Ctrl+S，导出当前视图（线宽保持 1 像素）")
        button("复位", self.reset_view, tip="F")
        button("纵轴自适应", self.autoscale_y, tip="A，按当前可视段自动缩放纵轴")

        tk.Frame(bar, bg="#D5D9DE", width=1, height=22).pack(side="left", padx=8, pady=8)

        self.var_grid = tk.BooleanVar(value=bool(self.cfg.get("style.grid_enabled", True)))
        ttk.Checkbutton(bar, text="网格", variable=self.var_grid,
                        command=self.toggle_grid).pack(side="left", padx=(0, 8))

        self.var_lock_x = tk.BooleanVar(value=False)
        self.var_lock_y = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="锁定 X 轴", variable=self.var_lock_x,
                        command=self._apply_locks).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(bar, text="锁定 Y 轴", variable=self.var_lock_y,
                        command=self._apply_locks).pack(side="left", padx=(0, 8))

        tk.Frame(bar, bg="#D5D9DE", width=1, height=22).pack(side="left", padx=8, pady=8)

        button("子图与设置", self.open_toolkit, tip="子图布局 + 修改 config.json 全部配置")
        button("帮助", self.show_help, tip="操作说明")

        self.info_label = tk.Label(
            bar, text="", bg=BG_BAR, fg="#666666", anchor="e",
            font=("Microsoft YaHei UI", 9),
        )
        self.info_label.pack(side="right", padx=10)

    # ---------------- 标签页 ----------------
    def _new_key(self) -> str:
        self._seq += 1
        return f"tab{self._seq}"

    def open_dialog(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择泰盟 BL 数据文件",
            filetypes=[("泰盟数据", "*.tmen"), ("所有文件", "*.*")],
        )
        for path in paths:
            self.open_file(path)

    def open_file(self, path: str | Path, activate: bool = True) -> Optional[str]:
        path = Path(path)
        try:
            data = read_tmen(path, self.cfg)
        except Exception as exc:
            messagebox.showerror("打开失败", f"{path.name}\n\n{exc}")
            self.set_status(f"打开失败：{exc}")
            return None

        if self._placeholder.winfo_exists():
            self._placeholder.pack_forget()

        key = self._new_key()
        page = PlotPage(self.content, data, self.cfg, self)
        self.pages[key] = page
        self.tabs.add(key, path.stem)
        self._show_page(key)
        self.set_status(self._describe(data))
        if data.notes:
            self.info_label.configure(text="；".join(data.notes[:2]))
        return key

    def _describe(self, data: TmenData) -> str:
        stim = f" | 刺激组 {len(data.stimuli)}" if data.stimuli else ""
        zero = ""
        if data.zero_mode_used not in ("none", None):
            zero = f" | 零点校正 {data.offset_applied:+.3f}"
        return (
            f"{data.name} | {data.n_samples} 点 | {data.fs:g} Hz | "
            f"{data.duration:.2f} s | {data.channel_name or '未知通道'}"
            f"{zero}{stim}"
        )

    def _show_page(self, key: str) -> None:
        for k, page in self.pages.items():
            if k == key:
                page.pack(side="top", fill="both", expand=True)
            else:
                page.pack_forget()

    def _on_tab_select(self, key: Optional[str]) -> None:
        if key is None:
            self._placeholder.pack(expand=True)
            return
        self._show_page(key)
        page = self.pages.get(key)
        if page is not None:
            self.var_lock_x.set(page.lock_x)
            self.var_lock_y.set(page.lock_y)
            self.set_status(self._describe(page.data))
            page.canvas.get_tk_widget().focus_set()

    def _on_tab_close(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        if self.cfg.get("app.confirm_close_tab", False):
            if not messagebox.askyesno("关闭标签页", f"关闭“{page.data.name}”？"):
                return
        page.destroy()
        self.pages.pop(key, None)
        self.tabs.remove(key)
        if not self.pages:
            self._placeholder.pack(expand=True)
            self.set_status("就绪 — 拖入 .tmen 文件，或点击“打开文件”")

    def current_page(self) -> Optional[PlotPage]:
        key = self.tabs.current_key
        return self.pages.get(key) if key else None

    def notify_title(self, page: PlotPage) -> None:
        for key, p in self.pages.items():
            if p is page:
                self.tabs.set_title(key, page.data.stem)
                return

    # ---------------- 工具栏动作 ----------------
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def reload_current(self) -> None:
        page = self.current_page()
        if page is None:
            return
        page.reload()
        self.set_status(self._describe(page.data))

    def save_image(self) -> None:
        page = self.current_page()
        if page is None:
            messagebox.showinfo("提示", "当前没有打开的图表")
            return
        default = f"{page.data.stem}.png"
        path = filedialog.asksaveasfilename(
            title="保存当前视图",
            defaultextension=".png",
            initialfile=default,
            filetypes=[("PNG 图片", "*.png"), ("PDF 文档", "*.pdf"),
                       ("SVG 矢量图", "*.svg"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            if path.lower().endswith((".pdf", ".svg")):
                page.fig.savefig(path, facecolor=self.cfg.get("style.figure_facecolor", "#FFFFFF"))
            else:
                page.export_png(path)
            self.set_status(f"已保存图片：{path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def reset_view(self) -> None:
        page = self.current_page()
        if page:
            page.reset_view()

    def autoscale_y(self) -> None:
        page = self.current_page()
        if page:
            page.autoscale_y()

    def toggle_grid(self) -> None:
        enabled = bool(self.var_grid.get())
        self.cfg.set("style.grid_enabled", enabled)
        for page in self.pages.values():
            if enabled:
                page.ax.set_axisbelow(True)
                from .style import px_to_pt
                page.ax.grid(
                    True,
                    color=self.cfg.get("style.grid_color", "#D2D2D2"),
                    linestyle=self.cfg.get("style.grid_linestyle", "--"),
                    linewidth=px_to_pt(self.cfg.get("style.grid_linewidth_px", 1.0),
                                       float(page.fig.get_dpi())),
                )
            else:
                page.ax.grid(False)
            page.canvas.draw_idle()

    def _apply_locks(self) -> None:
        page = self.current_page()
        if page is None:
            return
        page.lock_x = bool(self.var_lock_x.get())
        page.lock_y = bool(self.var_lock_y.get())

    def open_toolkit(self) -> None:
        if self.toolkit is not None and self.toolkit.winfo_exists():
            self.toolkit.lift()
            return
        self.toolkit = ToolkitWindow(self, self.current_page)

    def show_help(self) -> None:
        messagebox.showinfo(
            "操作说明",
            "【视图】\n"
            "  左键拖动　　　　平移（锁定的轴不动）\n"
            "  右键拖动　　　　框选放大\n"
            "  滚轮　　　　　　以光标为中心缩放横轴\n"
            "  Ctrl + 滚轮　　　以光标为中心缩放纵轴\n"
            "  Ctrl + 右键拖动　框选放大并锁定纵横比\n"
            "  双击　　　　　　复位到全图\n"
            "  ← / →　　　　　 左右平移\n"
            "  A / F　　　　　 纵轴自适应 / 复位全图\n\n"
            "【标签页】\n"
            "  打开文件 / 拖入 .tmen 均新建标签页；拖动标签可调整顺序；\n"
            "  标签上的 ✕ 关闭，Ctrl+W 关闭当前，Ctrl+O 打开文件，Ctrl+S 保存图片。\n\n"
            "【标注】\n"
            "  橙色竖线与文字为 .tmen 中 Stimulate 流记录的电刺激参数"
            "（强度 V / 频率 Hz / 通道 c）。\n"
            "  底部一行实时显示鼠标所在点的坐标，以及当前可视段的"
            "最小值、最大值、峰峰值。",
        )

    # ---------------- 配置 ----------------
    def apply_config(self, changed_sections: Optional[List[str]] = None) -> None:
        """应用配置：数据类参数变化时重新解析，样式类变化时重建图。"""
        sections = set(changed_sections or [])
        need_reload = bool(sections & {"data"})
        from .style import init_matplotlib

        init_matplotlib(self.cfg.font_list())
        self.root.title(str(self.cfg.get("app.title", "泰盟 BL .tmen 波形查看器")))
        self.var_grid.set(bool(self.cfg.get("style.grid_enabled", True)))

        for page in self.pages.values():
            if need_reload:
                page.reload()
            else:
                page.apply_config()
        if not self.pages:
            return
        self.set_status("设置已应用")

    def save_config(self) -> None:
        try:
            path = self.cfg.save()
            self.set_status(f"配置已保存：{path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    # ---------------- 快捷键 / 拖放 ----------------
    def _bind_shortcuts(self) -> None:
        r = self.root
        r.bind_all("<Control-o>", lambda e: self.open_dialog())
        r.bind_all("<Control-O>", lambda e: self.open_dialog())
        r.bind_all("<Control-s>", lambda e: self.save_image())
        r.bind_all("<Control-S>", lambda e: self.save_image())
        r.bind_all("<Control-w>", lambda e: self._close_current())
        r.bind_all("<Control-t>", lambda e: self.open_dialog())
        r.protocol("WM_DELETE_WINDOW", self.on_close)

    def _close_current(self) -> None:
        key = self.tabs.current_key
        if key:
            self._on_tab_close(key)

    def _bind_dnd(self) -> None:
        if not HAS_DND:
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event) -> None:
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [str(event.data).strip("{}")]
        for path in paths:
            if os.path.isfile(path):
                self.open_file(path)

    def on_close(self) -> None:
        try:
            if self.cfg.get("app.remember_geometry", True):
                geo = self.root.geometry().split("+")[0]
                w, h = geo.split("x")
                self.cfg.set("app.window_width", int(w))
                self.cfg.set("app.window_height", int(h))
                self.cfg.save()
        except Exception:
            pass
        self.root.destroy()


class _Tooltip:
    """极简悬停提示。"""

    def __init__(self, widget, text: str, delay: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._after = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip, text=self.text, bg="#FFF8DC", fg="#333333",
            relief="solid", bd=1, padx=6, pady=2,
            font=("Microsoft YaHei UI", 8),
        ).pack()

    def _hide(self, _event=None) -> None:
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        if self._tip:
            self._tip.destroy()
            self._tip = None
