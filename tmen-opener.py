import os
import struct
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox

import olefile
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib import rcParams

rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
rcParams["axes.unicode_minus"] = False

# 拖拽支持（可选）
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

# ---------- 解析参数 ----------
CHANNEL            = "Channel_Data1"
SMOOTH_WIN         = 1       # 1=不平滑；想更干净改 5、11
BASELINE_SUBTRACT  = True    # 减去前 2000 点均值
MAX_PLOT           = 12000   # 屏幕上最多画多少点


class App:
    def __init__(self, root):
        self.root = root
        self.t = None
        self.data = None
        self.fs = 1000.0
        self.home_xlim = None
        self.home_ylim = None
        self._drag = {"x": None, "xlim": None}

        self._build_ui()
        self._bind_mpl_events()
        self._bind_dnd()

    # ---------------- UI ----------------
    def _build_ui(self):
        r = self.root
        r.title("泰盟 BL .tmen 波形查看器")
        r.geometry("1200x720")

        top = tk.Frame(r, padx=8, pady=6)
        top.pack(side="top", fill="x")

        tk.Label(top, text="文件路径：").pack(side="left")
        self.path_var = tk.StringVar()
        self.entry = tk.Entry(top, textvariable=self.path_var)
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(top, text="浏览...", command=self.browse).pack(side="left", padx=2)
        tk.Button(top, text="绘图", command=self.plot_from_entry,
                  bg="#ffe0e0").pack(side="left", padx=2)

        hint_text = ("💡 也可以直接把 .tmen 文件拖进本窗口"
                     if HAS_DND else
                     "💡 想支持拖拽请先 pip install tkinterdnd2")
        tk.Label(r, text=hint_text, fg="#666", anchor="w").pack(side="top", fill="x", padx=10)

        # 状态栏（先 pack 到底部）
        self.status = tk.Label(r, text="就绪", anchor="w", relief="sunken", padx=8)
        self.status.pack(side="bottom", fill="x")

        # 绘图区
        self.fig = Figure(figsize=(12, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("等待载入文件...")
        self.ax.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.fig, master=r)
        widget = self.canvas.get_tk_widget()
        widget.pack(side="top", fill="both", expand=True, padx=8, pady=4)
        widget.bind("<Button-1>", lambda e: widget.focus_set())

        # 工具栏（保存图片、home、缩放等）
        tb_frame = tk.Frame(r)
        tb_frame.pack(side="bottom", fill="x")
        self.toolbar = NavigationToolbar2Tk(self.canvas, tb_frame)
        self.toolbar.update()

    # ---------------- DnD ----------------
    def _bind_dnd(self):
        if not HAS_DND:
            return
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.on_drop)

    def on_drop(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data.strip("{}")]
        if not paths:
            return
        path = paths[0]
        self.path_var.set(path)
        self.plot_file(path)

    # ---------------- 文件选择 ----------------
    def browse(self):
        path = filedialog.askopenfilename(
            title="选择泰盟 BL 数据文件",
            filetypes=[("泰盟数据", "*.tmen"), ("所有文件", "*.*")],
        )
        if path:
            self.path_var.set(path)

    def plot_from_entry(self):
        path = self.path_var.get().strip().strip('"')
        if not path:
            messagebox.showinfo("提示", "请先选择或拖入一个 .tmen 文件")
            return
        self.plot_file(path)

    # ---------------- 读数据 + 绘图 ----------------
    def plot_file(self, path):
        try:
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            if not olefile.isOleFile(path):
                raise ValueError("不是有效的 .tmen（OLE2）文件")

            ole = olefile.OleFileIO(path)
            if not ole.exists(CHANNEL):
                ole.close()
                raise ValueError(f"文件里没有 {CHANNEL} 流，可能不是泰盟 BL 数据")

            raw = ole.openstream(CHANNEL).read()

            fs = 1000.0
            if ole.exists("Config"):
                cfg = ole.openstream("Config").read()
                if len(cfg) >= 0x4A:
                    try:
                        fs_try = struct.unpack("<f", cfg[0x46:0x4A])[0]
                        if 10 < fs_try < 1e6:
                            fs = float(fs_try)
                    except struct.error:
                        pass
            ole.close()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            self.status.config(text="读取失败：" + str(e))
            return

        arr = np.frombuffer(raw, dtype="<f4").astype(np.float64)
        if arr.size == 0:
            messagebox.showerror("错误", "数据为空")
            return

        n = len(arr)
        baseline = arr[:min(2000, n)].mean() if BASELINE_SUBTRACT else 0.0
        data = arr - baseline
        if SMOOTH_WIN > 1:
            k = np.ones(SMOOTH_WIN) / SMOOTH_WIN
            data = np.convolve(data, k, mode="same")
        t = np.arange(n) / fs
        step = max(1, n // MAX_PLOT)

        self.t, self.data, self.fs = t, data, fs

        ax = self.ax
        ax.clear()
        ax.plot(t[::step], data[::step], color="red", linewidth=0.8)
        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("幅值（去基线）" if BASELINE_SUBTRACT else "幅值")
        ax.set_title(f"{os.path.basename(path)}   |   {n} 点   {n/fs:.3f}s   FS={fs:g} Hz")
        ax.grid(True, alpha=0.3)
        ax.format_coord = lambda x, y: f"t={x:.4g}s, y={y:.4f}"
        ax.relim()
        ax.autoscale_view()
        self.fig.tight_layout()
        self.canvas.draw_idle()

        self.home_xlim = ax.get_xlim()
        self.home_ylim = ax.get_ylim()

        self.status.config(
            text=f"{os.path.basename(path)}   |   点数 {n}   |   "
                 f"峰峰值 {data.max()-data.min():.4f}   |   时长 {n/fs:.3f}s   |   FS={fs:g}Hz"
        )
        self.canvas.get_tk_widget().focus_set()

        print("=== 载入 ===")
        print("文件     :", path)
        print("点数     :", n)
        print("采样率   :", fs)
        print("时长     :", f"{n/fs:.3f} s")
        print("原始范围 :", f"{arr.min():.6f} ~ {arr.max():.6f}")
        print("去基线   :", f"{data.min():.6f} ~ {data.max():.6f}")
        print("峰峰值   :", f"{data.max()-data.min():.6f}")

    # ---------------- Matplotlib 交互 ----------------
    def _bind_mpl_events(self):
        c = self.canvas
        c.mpl_connect("scroll_event", self.on_scroll)
        c.mpl_connect("key_press_event", self.on_key)
        c.mpl_connect("button_press_event", self.on_press)
        c.mpl_connect("motion_notify_event", self.on_motion)
        c.mpl_connect("button_release_event", self.on_release)

    def on_scroll(self, event):
        if event.inaxes is not self.ax or event.xdata is None:
            return
        x0, x1 = self.ax.get_xlim()
        xd = event.xdata
        scale = 0.85 if event.button == "up" else 1 / 0.85
        new_w = max((x1 - x0) * scale, 1e-4)
        rel = (x1 - xd) / (x1 - x0)
        self.ax.set_xlim(xd - new_w * (1 - rel), xd + new_w * rel)
        self.canvas.draw_idle()

    def on_key(self, event):
        if event.key in ("left", "right"):
            x0, x1 = self.ax.get_xlim()
            w = x1 - x0
            step = w * 0.25
            if event.key == "left":
                self.ax.set_xlim(x0 - step, x1 - step)
            else:
                self.ax.set_xlim(x0 + step, x1 + step)
            self.canvas.draw_idle()
        elif event.key in ("a", "A") and self.t is not None:
            x0, x1 = self.ax.get_xlim()
            mask = (self.t >= x0) & (self.t <= x1)
            if np.any(mask):
                y0, y1 = self.data[mask].min(), self.data[mask].max()
                pad = max((y1 - y0) * 0.08, 1e-6)
                self.ax.set_ylim(y0 - pad, y1 + pad)
                self.canvas.draw_idle()

    def on_press(self, event):
        # 右键按住开始拖拽
        if event.button == 3 and event.inaxes is self.ax and event.xdata is not None:
            self._drag["x"] = event.xdata
            self._drag["xlim"] = self.ax.get_xlim()
        # 左键双击重置
        if event.dblclick and event.button == 1 and event.inaxes is self.ax:
            if self.home_xlim is not None:
                self.ax.set_xlim(self.home_xlim)
                self.ax.set_ylim(self.home_ylim)
                self.canvas.draw_idle()

    def on_motion(self, event):
        if self._drag["x"] is None or event.inaxes is not self.ax or event.xdata is None:
            return
        dx = self._drag["x"] - event.xdata
        x0, x1 = self._drag["xlim"]
        self.ax.set_xlim(x0 + dx, x1 + dx)
        self.canvas.draw_idle()

    def on_release(self, event):
        if event.button == 3:
            self._drag["x"] = None


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
