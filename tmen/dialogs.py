"""对话框：Subplot configuration tool（子图布局 + 全部设置）。

设置界面完全由 :data:`tmen.config.FIELD_TABLE` 自动生成，
配置文件里加一项，这里就自动多一个控件，因此"可以修改配置文件中的一切内容"。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont
from typing import Any, Dict, List

from .config import FIELD_TABLE, build_defaults, fields_of


# --------------------------------------------------------------------------- #
# 可滚动容器
# --------------------------------------------------------------------------- #
class ScrollFrame(ttk.Frame):
    """带竖向滚动条的容器，内部用 ``.body`` 放控件。"""

    def __init__(self, master, **kw) -> None:
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#FFFFFF")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body = tk.Frame(self.canvas, bg="#FFFFFF")
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_wheel(False))

    def _on_body(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, active: bool) -> None:
        if active:
            self.canvas.bind_all("<MouseWheel>", self._wheel)
            self.canvas.bind_all("<Button-4>", self._wheel)
            self.canvas.bind_all("<Button-5>", self._wheel)
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.canvas.unbind_all(seq)

    def _wheel(self, event) -> None:
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta * 2, "units")


# --------------------------------------------------------------------------- #
# 子图布局面板
# --------------------------------------------------------------------------- #
class SubplotPanel(ttk.Frame):
    """左/右/上/下边距与间距滑杆（等价于 matplotlib 的 Configure subplots）。"""

    ITEMS = [
        ("left", "左边距", 0.0, 1.0),
        ("right", "右边距", 0.0, 1.0),
        ("bottom", "下边距", 0.0, 1.0),
        ("top", "上边距", 0.0, 1.0),
        ("wspace", "水平间距", 0.0, 1.0),
        ("hspace", "垂直间距", 0.0, 1.0),
    ]

    def __init__(self, master, app, page_provider) -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.page_provider = page_provider
        self.vars: Dict[str, tk.DoubleVar] = {}
        self.value_labels: Dict[str, ttk.Label] = {}

        cfg = app.cfg
        head = ttk.Label(
            self,
            text="拖动滑杆实时调整当前图表的绘图区边距；点“保存为默认”会写入 config.json。",
            foreground="#404040",
        )
        head.pack(anchor="w", pady=(0, 8))

        for key, label, lo, hi in self.ITEMS:
            row = ttk.Frame(self)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=10).pack(side="left")
            var = tk.DoubleVar(value=float(cfg.get(f"subplot.{key}", 0.1)))
            self.vars[key] = var
            scale = ttk.Scale(
                row, from_=lo, to=hi, variable=var, orient="horizontal",
                command=lambda _v, k=key: self._on_change(k),
            )
            scale.pack(side="left", fill="x", expand=True, padx=6)
            val = ttk.Label(row, text=f"{var.get():.3f}", width=7, anchor="e")
            val.pack(side="left")
            self.value_labels[key] = val

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="恢复默认", command=self.reset_defaults).pack(side="left")
        ttk.Button(btns, text="保存为默认", command=self.save_defaults).pack(side="left", padx=6)
        ttk.Button(btns, text="应用到所有标签页", command=self.apply_to_all).pack(side="left")

        hint = ttk.Label(
            self,
            text=("提示：右侧“全部设置”里可以修改颜色、线宽、横轴时间格式、"
                  "刺激标注模板、鼠标缩放系数等全部配置项。"),
            foreground="#666666", wraplength=520, justify="left",
        )
        hint.pack(anchor="w", pady=(12, 0))

    def _current_page(self):
        return self.page_provider()

    def _on_change(self, key: str) -> None:
        value = float(self.vars[key].get())
        self.value_labels[key].configure(text=f"{value:.3f}")
        page = self._current_page()
        if page is None:
            return
        kwargs = {k: float(v.get()) for k, v in self.vars.items()}
        try:
            page.fig.subplots_adjust(**kwargs)
            page.canvas.draw_idle()
        except Exception:
            pass

    def _push_values(self) -> None:
        for key, var in self.vars.items():
            self.app.cfg.set(f"subplot.{key}", float(var.get()))
            self.value_labels[key].configure(text=f"{var.get():.3f}")

    def apply_to_all(self) -> None:
        self._push_values()
        for page in self.app.pages:
            try:
                page.fig.subplots_adjust(**{k: float(v.get()) for k, v in self.vars.items()})
                page.canvas.draw_idle()
            except Exception:
                pass
        self.app.set_status("子图边距已应用到全部标签页（尚未写入文件）")

    def reset_defaults(self) -> None:
        defaults = build_defaults()["subplot"]
        for key, var in self.vars.items():
            var.set(float(defaults.get(key, 0.1)))
        self._on_change("left")

    def save_defaults(self) -> None:
        self._push_values()
        self.app.save_config()
        self.app.set_status("子图边距已保存到 config.json")


# --------------------------------------------------------------------------- #
# 全部设置面板
# --------------------------------------------------------------------------- #
class SettingsPanel(ttk.Frame):
    """按 FIELD_TABLE 自动生成的完整设置表单。"""

    def __init__(self, master, app) -> None:
        super().__init__(master)
        self.app = app
        self.cfg = app.cfg
        self.vars: Dict[str, tk.Variable] = {}
        self._color_buttons: Dict[str, tk.Button] = {}

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.body

        small = tkfont.nametofont("TkDefaultFont").copy()
        small.configure(size=max(8, small.cget("size") - 1))

        for section, label, fields in FIELD_TABLE:
            box = tk.LabelFrame(
                body, text=f"  {label} ",
                font=small, bg="#FFFFFF", fg="#1858B8", bd=1, relief="groove",
                padx=8, pady=6,
            )
            box.pack(fill="x", padx=8, pady=6)
            grid = tk.Frame(box, bg="#FFFFFF")
            grid.pack(fill="x", padx=(0, 6))
            grid.columnconfigure(1, weight=1)
            grid.columnconfigure(3, weight=1)

            for index, (key, name, default, kind, extra) in enumerate(fields):
                dotted = f"{section}.{key}"
                row = index // 2
                col = (index % 2) * 3
                tk.Label(grid, text=name, bg="#FFFFFF", fg="#333333",
                         font=small, anchor="w").grid(
                    row=row, column=col, sticky="w", padx=(0, 4), pady=2)
                self._make_widget(grid, row, col + 1, dotted, default, kind, extra, small)
            # 空行补齐
            grid.grid_columnconfigure(1, minsize=120, weight=1)
            grid.grid_columnconfigure(4, minsize=120, weight=1)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=6)
        ttk.Button(bottom, text="应用", command=self.apply).pack(side="left")
        ttk.Button(bottom, text="保存到 config.json", command=self.save).pack(side="left", padx=6)
        ttk.Button(bottom, text="恢复默认", command=self.reset).pack(side="left")
        ttk.Button(bottom, text="打开配置文件所在的文件夹",
                   command=self.reveal_config).pack(side="right")

    # ---------------- 控件工厂 ----------------
    def _make_widget(self, parent, row, col, dotted, default, kind, extra, font) -> None:
        value = self.cfg.get(dotted, default)

        if kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(parent, variable=var).grid(
                row=row, column=col, sticky="w", pady=1)
            self.vars[dotted] = var
            return

        if kind == "choice":
            var = tk.StringVar(value=str(value))
            combo = ttk.Combobox(parent, textvariable=var, values=list(extra or []),
                                 width=12, state="readonly", font=font)
            combo.grid(row=row, column=col, sticky="w", pady=1)
            self.vars[dotted] = var
            return

        if kind in ("int", "float"):
            var = tk.StringVar(value=str(value))
            lo, hi, step = (extra or (None, None, None))
            spin = ttk.Spinbox(
                parent, textvariable=var, width=12, font=font,
                from_=lo, to=hi, increment=step if step else 1,
            )
            spin.grid(row=row, column=col, sticky="w", pady=1)
            self.vars[dotted] = var
            return

        if kind == "color":
            holder = tk.Frame(parent, bg="#FFFFFF")
            holder.grid(row=row, column=col, sticky="w", pady=1)
            var = tk.StringVar(value=str(value))
            btn = tk.Button(
                holder, text="", width=3, relief="groove", bd=1,
                bg=str(value) if str(value).startswith("#") else "#FFFFFF",
                command=lambda: self._pick_color(dotted, var),
            )
            btn.pack(side="left")
            entry = ttk.Entry(holder, textvariable=var, width=8, font=font)
            entry.pack(side="left", padx=(4, 0))
            var.trace_add("write", lambda *_a, d=dotted, b=btn, v=var: self._sync_color(d, b, v))
            self._color_buttons[dotted] = btn
            self.vars[dotted] = var
            return

        var = tk.StringVar(value=str(value))
        entry = ttk.Entry(parent, textvariable=var, width=14, font=font)
        entry.grid(row=row, column=col, sticky="we", padx=(0, 8), pady=1)
        self.vars[dotted] = var

    def _sync_color(self, dotted: str, btn: tk.Button, var: tk.StringVar) -> None:
        text = var.get().strip()
        if text.startswith("#") and len(text) in (4, 7):
            try:
                btn.configure(bg=text)
            except tk.TclError:
                pass

    def _pick_color(self, dotted: str, var: tk.StringVar) -> None:
        initial = var.get().strip() or "#FFFFFF"
        _rgb, hex_color = colorchooser.askcolor(color=initial, title="选择颜色")
        if hex_color:
            var.set(hex_color.upper())

    # ---------------- 动作 ----------------
    def _collect(self) -> List[str]:
        """把界面上的值写回配置，返回被修改的顶层小节名。"""
        changed_sections = set()
        for dotted, var in self.vars.items():
            section, key = dotted.split(".", 1)
            old = self.cfg.get(dotted)
            raw = var.get()
            field = next((f for f in fields_of(section) if f[0] == key), None)
            kind = field[3] if field else "str"
            try:
                if kind == "bool":
                    new: Any = bool(raw)
                elif kind == "int":
                    new = int(round(float(raw)))
                elif kind == "float":
                    new = float(raw)
                else:
                    new = str(raw)
            except (TypeError, ValueError):
                messagebox.showwarning("数值无效", f"“{dotted}”不是合法数值，已跳过。")
                continue
            if isinstance(old, (int, float)) and not isinstance(old, bool) and kind in ("int", "float"):
                pass
            if new != old:
                self.cfg.set(dotted, new)
                changed_sections.add(section)
        return sorted(changed_sections)

    def apply(self) -> None:
        changed = self._collect()
        self.app.apply_config(changed_sections=changed)
        self.app.set_status(f"设置已应用（受影响小节：{', '.join(changed) or '无'}）")

    def save(self) -> None:
        self._collect()
        self.app.apply_config(changed_sections=None)
        self.app.save_config()

    def reset(self) -> None:
        if not messagebox.askyesno("恢复默认", "把所有设置恢复为程序默认值？"):
            return
        self.cfg.reset()
        for dotted, var in self.vars.items():
            default = self.cfg.get(dotted)
            var.set(str(default) if not isinstance(default, bool) else bool(default))
        for dotted, btn in self._color_buttons.items():
            self._sync_color(dotted, btn, self.vars[dotted])
        self.app.apply_config(changed_sections=None)

    def reveal_config(self) -> None:
        path = self.app.cfg.path
        try:
            self.app.cfg.save()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        import subprocess
        import sys
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception:
            messagebox.showinfo("配置文件位置", str(path))


# --------------------------------------------------------------------------- #
# 主窗口
# --------------------------------------------------------------------------- #
class ToolkitWindow(tk.Toplevel):
    """Subplot configuration tool 窗口：子图布局 + 全部设置两个页签。"""

    def __init__(self, app, page_provider) -> None:
        super().__init__(app.root)
        self.app = app
        self.title("Subplot configuration tool — 子图布局 / 全部设置")
        self.minsize(820, 520)
        try:
            self.transient(app.root)

            root = app.root
            root.update_idletasks()
            w, h = 1000, 700
            x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
            y = root.winfo_rooty() + max(0, (root.winfo_height() - h) // 3)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.geometry("1000x700")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.subplot_panel = SubplotPanel(nb, app, page_provider)
        self.settings_panel = SettingsPanel(nb, app)
        nb.add(self.subplot_panel, text="  子图布局  ")
        nb.add(self.settings_panel, text="  全部设置 (config.json)  ")
        self.notebook = nb

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text="关闭", command=self.destroy).pack(side="right")

    def focus_settings(self) -> None:
        self.notebook.select(self.settings_panel)
