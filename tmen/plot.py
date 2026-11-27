"""单张波形的绘图与交互（一个标签页 = 一个 PlotPage）。

交互约定（与泰盟 BL 软件一致，全部单击即生效，无需先按工具栏按钮）：

======================  ==================================================
左键拖动                 平移（锁定轴后该方向不动）
右键拖动                 框选缩放（矩形区域放大）
滚轮                     以光标为中心缩放横轴
Ctrl + 滚轮              以光标为中心缩放纵轴
Ctrl + 右键拖动           框选缩放并锁定纵横比（等比缩放）
双击                     复位到全图
← / →                    左右平移
A                        纵轴自适应当前可视段
F                        复位全图
======================  ==================================================
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter

from .config import Config
from .parser import DEFAULT_STIMULUS_LABEL, TmenData, read_tmen
from .style import TimeFormatter, apply_axes_style, apply_figure_style, format_time, px_to_pt

CURSOR_DEFAULT = ""
CURSOR_PAN = "fleur"


class PlotPage(tk.Frame):
    """一个标签页：画布 + 底部读数栏。"""

    def __init__(self, master, data: TmenData, cfg: Config, app) -> None:
        super().__init__(master, bg="#FFFFFF")
        self.app = app
        self.cfg = cfg
        self.data = data

        self.lock_x = False
        self.lock_y = False

        self._bg = None
        self._pan: Optional[dict] = None
        self._rubber: Optional[dict] = None
        self._hover_index: Optional[int] = None
        self._stim_labels: List = []

        self._build_widgets()
        self._build_figure()
        self._bind_events()
        self.load(data)

    # ------------------------------------------------------------------ 构建
    def _build_widgets(self) -> None:
        self.info = tk.Frame(self, bg="#F4F6F8", height=24)
        self.info.pack(side="bottom", fill="x")
        self.info_left = tk.Label(
            self.info, text="—", anchor="w", bg="#F4F6F8", fg="#1858B8",
            font=("Consolas", 9), padx=8, pady=3,
        )
        self.info_left.pack(side="left")
        self.info_right = tk.Label(
            self.info, text="", anchor="e", bg="#F4F6F8", fg="#404040",
            font=("Consolas", 9), padx=8, pady=3,
        )
        self.info_right.pack(side="right")

        self.plot_area = tk.Frame(self, bg="#FFFFFF")
        self.plot_area.pack(side="top", fill="both", expand=True)

    def _build_figure(self) -> None:
        dpi = float(self.cfg.get("app.dpi", 100))
        self.fig = Figure(figsize=(9.0, 4.6), dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_area)
        self.canvas.get_tk_widget().configure(
            bg=self.cfg.get("style.figure_facecolor", "#FFFFFF"),
            highlightthickness=0, bd=0,
        )
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        self._time_fmt = TimeFormatter(str(self.cfg.get("time_axis.format", "mm:ss.mmm")))
        self.ax.xaxis.set_major_formatter(self._time_fmt)
        self._home_xlim = (0.0, 1.0)
        self._home_ylim = (0.0, 1.0)

    # ------------------------------------------------------------------ 载入
    def load(self, data: TmenData) -> None:
        self.data = data
        self._prepare_axes()
        self.canvas.draw()
        self._bg = self.canvas.copy_from_bbox(self.ax.bbox)
        self.hide_hover()
        self.app.notify_title(self)

    def reload(self, keep_view: bool = False) -> bool:
        """按当前配置重新解析文件（改平滑 / 零点 / 数据流后调用）。"""
        try:
            data = read_tmen(self.data.path, self.cfg)
        except Exception as exc:  # 解析失败时保留旧数据
            self.app.set_status(f"重新载入失败：{exc}")
            return False
        if keep_view:
            self.data = data
            self.apply_config()
        else:
            self.load(data)
        return True

    # ------------------------------------------------------------------ 绘图
    def _prepare_axes(self) -> None:
        cfg = self.cfg
        ax = self.ax
        ax.clear()

        apply_figure_style(self.fig, cfg)
        apply_axes_style(
            ax, cfg,
            xlabel=str(cfg.get("style.xlabel", "时间")),
            ylabel=self._ylabel(),
            title=self._title(),
        )
        self._time_fmt.set_style(str(cfg.get("time_axis.format", "mm:ss.mmm")))
        ax.xaxis.set_major_formatter(self._time_fmt)
        ax.yaxis.set_major_formatter(FuncFormatter(self._y_formatter()))

        dpi = float(self.fig.get_dpi())
        self._line, = ax.plot(
            [], [],
            color=cfg.get("style.waveform_color", "#D0021B"),
            linewidth=px_to_pt(cfg.get("style.waveform_linewidth_px", 1.0), dpi),
            antialiased=bool(cfg.get("style.antialiased", False)),
            solid_capstyle="butt",
            solid_joinstyle="miter",
            zorder=4,
        )

        # 横向用采样时间，纵向贴住横轴，随横轴缩放而不受纵轴缩放影响。
        axis_transform = ax.get_xaxis_transform()
        self._stim_lines = LineCollection(
            [],
            colors=[cfg.get("stimulus.marker_color", "#008000")],
            linewidths=[px_to_pt(cfg.get("stimulus.marker_linewidth_px", 1.0), dpi)],
            linestyles=[cfg.get("stimulus.marker_linestyle", "-")],
            transform=axis_transform, antialiaseds=False, zorder=5,
        )
        ax.add_collection(self._stim_lines, autolim=False)

        self._stim_bands = PolyCollection(
            [],
            facecolors=[cfg.get("stimulus.band_color", "#008000")],
            alpha=float(cfg.get("stimulus.band_alpha", 0.2)),
            edgecolors="none", zorder=3, transform=axis_transform,
        )
        ax.add_collection(self._stim_bands, autolim=False)

        template = str(cfg.get("stimulus.label_template", DEFAULT_STIMULUS_LABEL))
        self._stim_labels = [
            ax.text(
                group.t0, 0.0, group.label(template), transform=axis_transform,
                ha="center", va="bottom", fontsize=float(cfg.get("stimulus.label_size", 7.0)),
                color=cfg.get("stimulus.label_color", "#008000"),
                zorder=7, clip_on=True, visible=False,
            )
            for group in self.data.stimuli
        ]

        # 悬浮标记（animated：普通重绘不画它，靠 blit 单独刷新，鼠标移动才不卡）
        self._hover_pt, = ax.plot(
            [], [], marker="o", markersize=5.0, linestyle="none",
            markerfacecolor="#FFFFFF",
            markeredgecolor=cfg.get("style.waveform_color", "#D0021B"),
            markeredgewidth=1.2, zorder=9,
            animated=True, visible=False,
        )
        self._hover_v = ax.axvline(
            0.0, color="#1858B8", linewidth=px_to_pt(1.0, dpi), alpha=0.35,
            zorder=2, animated=True, visible=False,
        )
        self._rubber_patch = Rectangle(
            (0, 0), 0, 0, facecolor="#1858B8", alpha=0.10,
            edgecolor="#1858B8", linewidth=px_to_pt(1.0, dpi),
            visible=False, zorder=10, animated=True,
        )
        ax.add_patch(self._rubber_patch)

        # Event 流标记（可选，静态 artist，缩放时自动跟随）
        if cfg.get("events.enabled", False) and self.data.events:
            color = cfg.get("events.color", "#7A7A7A")
            tpl = str(cfg.get("events.label_template", "{value:g}"))
            labels_by_time = {}
            for ev in self.data.events:
                try:
                    text = tpl.format(value=ev.value, t=ev.time, kind=ev.kind)
                except Exception:
                    text = f"{ev.value:g}"
                labels_by_time.setdefault(ev.time, []).append(text)
            for time, labels in labels_by_time.items():
                ax.axvline(time, color=color, linestyle=":", linewidth=px_to_pt(1.0, dpi),
                           alpha=0.8, zorder=2)
                ax.text(time, 0.985, "\n".join(labels), transform=axis_transform, ha="left", va="top",
                    fontsize=float(cfg.get("events.size", 7.0)), color=color,
                    zorder=6, clip_on=True)

        self._home_ylim = self._calc_ylim(0, self.data.n_samples)
        pad_ratio = float(cfg.get("time_axis.right_pad_ratio", 0.006))
        duration = max(self.data.duration, 1e-6)
        self._home_xlim = (0.0, duration * (1.0 + max(0.0, pad_ratio)))
        ax.set_xlim(*self._home_xlim)
        ax.set_ylim(*self._home_ylim)

        self.refresh(redraw=True)

    def _ylabel(self) -> str:
        cfg = self.cfg
        mode = cfg.get("style.ylabel_mode", "channel")
        if mode == "none":
            return ""
        if mode == "custom":
            return str(cfg.get("style.ylabel_custom", ""))
        return self.data.ylabel(cfg.unit_map())

    def _title(self) -> str:
        tpl = str(self.cfg.get("style.title_template", "{name}"))
        try:
            return tpl.format(
                name=self.data.name, stem=self.data.stem,
                channel=self.data.channel_name, experiment=self.data.experiment,
            )
        except Exception:
            return self.data.name

    def _y_formatter(self):
        fmt = str(self.cfg.get("y_axis.format", "%.2f"))

        def _fmt(value, pos=None):
            try:
                if abs(value) >= 1e7:
                    return f"{value:.3g}"
                return fmt % value
            except (TypeError, ValueError):
                return f"{value:g}"

        return _fmt

    # ------------------------------------------------------------------ 曲线
    def _index_range(self) -> Tuple[int, int]:
        x0, x1 = self.ax.get_xlim()
        fs = self.data.fs
        n = self.data.n_samples
        if fs <= 0:
            return 0, n
        i0 = int(math.floor(min(x0, x1) * fs)) - 1
        i1 = int(math.ceil(max(x0, x1) * fs)) + 2
        return max(0, min(n, i0)), max(0, min(n, i1))

    def _decimate(self, i0: int, i1: int) -> Tuple[np.ndarray, np.ndarray]:
        """像素列 min/max 包络降采样：屏幕上一列只画最值，峰谷不丢，速度够快。"""
        y = self.data.y[i0:i1]
        n = y.size
        if n == 0:
            return np.empty(0), np.empty(0)

        try:
            width_px = max(64.0, float(self.ax.bbox.width))
        except Exception:
            width_px = 900.0
        target = float(self.cfg.get("app.max_points_per_curve", 4000))
        ncols = int(min(width_px, target, n))
        if n <= ncols * 2 or ncols < 2:
            return self.data.t[i0:i1], y

        edges = np.unique(np.linspace(0, n, ncols + 1).astype(np.int64))
        starts = edges[:-1]
        if starts.size < 2:
            return self.data.t[i0:i1], y
        mins = np.minimum.reduceat(y, starts)
        maxs = np.maximum.reduceat(y, starts)
        xs = np.repeat(self.data.t[i0 + starts], 2)
        ys = np.empty(mins.size * 2, dtype=np.float64)
        ys[0::2] = mins
        ys[1::2] = maxs
        return xs, ys

    def refresh(self, redraw: bool = True) -> None:
        """按当前坐标范围重画曲线 / 刺激标注 / 底部读数。"""
        i0, i1 = self._index_range()
        xs, ys = self._decimate(i0, i1)
        self._line.set_data(xs, ys)
        self._update_stimulus()
        self._update_stats(i0, i1)
        if redraw:
            self.canvas.draw_idle()

    def _update_stimulus(self) -> None:
        cfg = self.cfg
        ax = self.ax
        for text in self._stim_labels:
            text.set_visible(False)
        if not cfg.get("stimulus.enabled", True) or not self.data.stimuli:
            self._stim_lines.set_segments([])
            self._stim_bands.set_verts([])
            return

        x0, x1 = sorted(ax.get_xlim())
        left, bottom, width, height = ax.bbox.bounds
        if width <= 10 or height <= 10:
            self._stim_lines.set_segments([])
            self._stim_bands.set_verts([])
            return

        font_px = float(cfg.get("stimulus.label_size", 7.0)) * self.fig.dpi / 72.0
        tick_bottom = (font_px + 5) / height
        tick_top = tick_bottom + 9 / height
        row_step = max(float(cfg.get("stimulus.label_row_step", 0.048)),
                       (font_px + 5) / height)
        row_count = max(1, int(cfg.get("stimulus.label_rows", 2)))
        row_positions = [2 / height + i * row_step for i in range(row_count)
                         if (2 + font_px) / height + i * row_step < 1]
        min_gap = float(cfg.get("stimulus.label_min_gap_px", 8))
        pixels_per_second = width / (x1 - x0)
        show_marker = cfg.get("stimulus.show_marker", True)
        show_band = cfg.get("stimulus.show_band", False)
        segments, bands, candidates = [], [], []
        for group, label in zip(self.data.stimuli, self._stim_labels):
            if group.t1 < x0 or group.t0 > x1:
                continue
            visible_times = [r.time for r in group.records if x0 <= r.time <= x1]
            if not group.records and x0 <= group.t0 <= x1:
                visible_times = [group.t0]
            if len(visible_times) > 1:
                # 全览时相邻脉冲可能落在同一像素，放大后再逐条显示。
                spread_px = (visible_times[-1] - visible_times[0]) * pixels_per_second
                if spread_px < 4 * (len(visible_times) - 1):
                    visible_times = visible_times[:1]
            if show_marker:
                segments.extend([(t, tick_bottom), (t, tick_top)] for t in visible_times)
            if show_band and group.duration > 0:
                start, end = max(group.t0, x0), min(group.t1, x1)
                bands.append([(start, tick_bottom), (start, tick_top),
                              (end, tick_top), (end, tick_bottom)])
            anchor = visible_times[0] if visible_times else max(x0, group.t0)
            candidates.append((group.n_records, anchor, label))

        self._stim_lines.set_segments(segments)
        self._stim_bands.set_verts(bands)
        if not candidates:
            return

        renderer = self.canvas.get_renderer()
        occupied: List[List[Tuple[float, float]]] = [[] for _ in row_positions]
        for _n_records, anchor, label in sorted(candidates, key=lambda item: (-item[0], item[1])):
            anchor_px, _ = ax.get_xaxis_transform().transform((anchor, 0))
            label.set_visible(True)
            half = label.get_window_extent(renderer).width / 2
            label.set_visible(False)
            if 2 * half > width - 4:
                continue
            center = min(max(anchor_px, left + half + 2), left + width - half - 2)
            start, end = center - half, center + half
            for row_y, boxes in zip(row_positions, occupied):
                if any(start < b + min_gap and end + min_gap > a for a, b in boxes):
                    continue
                boxes.append((start, end))
                time, _ = ax.transData.inverted().transform((center, bottom))
                label.set_position((time, row_y))
                label.set_visible(True)
                break

    def _update_stats(self, i0: int, i1: int) -> None:
        cfg = self.cfg
        seg = self.data.y[i0:i1]
        if seg.size == 0:
            self.info_right.configure(text="")
            return
        seg = seg[np.isfinite(seg)]
        if seg.size == 0:
            self.info_right.configure(text="")
            return

        vmin = float(seg.min())
        vmax = float(seg.max())
        p2p = vmax - vmin
        prec = int(cfg.get("status.precision", 3))
        unit = self.data.unit(cfg.unit_map())
        unit_txt = f" {unit}" if unit else ""

        parts = []
        if cfg.get("status.show_min_max", True):
            parts.append(f"最小 {vmin:.{prec}f}{unit_txt}   最大 {vmax:.{prec}f}{unit_txt}")
        if cfg.get("status.show_peak_to_peak", True):
            parts.append(f"峰峰值 {p2p:.{prec}f}{unit_txt}")
        x0, x1 = self.ax.get_xlim()
        style = str(cfg.get("time_axis.format", "mm:ss.mmm"))
        parts.append(f"视图 {format_time(max(0.0, x0), style)} ~ {format_time(max(0.0, x1), style)}")
        self.info_right.configure(text="     ".join(parts))

    def _calc_ylim(self, i0: int, i1: int) -> Tuple[float, float]:
        seg = self.data.y[max(0, i0):max(1, i1)]
        seg = seg[np.isfinite(seg)]
        if seg.size == 0:
            return 0.0, 1.0
        lo, hi = float(seg.min()), float(seg.max())
        if hi - lo < 1e-9:
            pad = max(abs(hi) * 0.05, 1e-3)
        else:
            pad = (hi - lo) * float(self.cfg.get("y_axis.autoscale_padding", 0.06))
        return lo - pad, hi + pad

    # ------------------------------------------------------------------ 交互
    def _bind_events(self) -> None:
        c = self.canvas
        c.mpl_connect("scroll_event", self.on_scroll)
        c.mpl_connect("button_press_event", self.on_press)
        c.mpl_connect("button_release_event", self.on_release)
        c.mpl_connect("motion_notify_event", self.on_motion)
        c.mpl_connect("draw_event", self.on_draw)
        c.mpl_connect("key_press_event", self.on_key)
        c.mpl_connect("resize_event", self.on_resize)
        widget = c.get_tk_widget()
        widget.bind("<Enter>", lambda e: widget.focus_set())

    def on_resize(self, event) -> None:
        # 画布尺寸变了，标注文字的像素位置要重算
        self.refresh(redraw=False)

    def on_draw(self, event) -> None:
        try:
            self._bg = self.canvas.copy_from_bbox(self.ax.bbox)
        except Exception:
            self._bg = None

    @staticmethod
    def _has_ctrl(event) -> bool:
        key = getattr(event, "key", None)
        return isinstance(key, str) and ("ctrl" in key or "control" in key)

    # ---------------- 滚轮缩放 ----------------
    def on_scroll(self, event) -> None:
        if event.inaxes is not self.ax or event.xdata is None or event.ydata is None:
            return
        factor = float(self.cfg.get("interaction.wheel_zoom_factor", 0.85))
        if not (0.05 < factor < 1.0):
            factor = 0.85
        scale = factor if event.button == "up" else 1.0 / factor
        ctrl = self._has_ctrl(event)

        if ctrl:
            if not self.cfg.get("interaction.ctrl_wheel_zoom_y", True):
                return
            if self.lock_y:
                return
            y0, y1 = self.ax.get_ylim()
            new_h = (y1 - y0) * scale
            rel = (y1 - event.ydata) / (y1 - y0) if y1 > y0 else 0.5
            self.ax.set_ylim(event.ydata - new_h * (1 - rel), event.ydata + new_h * rel)
        else:
            if not self.cfg.get("interaction.wheel_zoom_x", True):
                return
            if self.lock_x:
                return
            x0, x1 = self.ax.get_xlim()
            min_span = float(self.cfg.get("interaction.min_span_s", 5e-4))
            new_w = max((x1 - x0) * scale, min_span)
            rel = (x1 - event.xdata) / (x1 - x0) if x1 > x0 else 0.5
            self.ax.set_xlim(event.xdata - new_w * (1 - rel), event.xdata + new_w * rel)
        self.refresh()

    # ---------------- 按下 ----------------
    def on_press(self, event) -> None:
        if event.inaxes is not self.ax or event.xdata is None:
            return
        self.canvas.get_tk_widget().focus_set()

        if event.button == 1 and event.dblclick and self.cfg.get("interaction.double_click_reset", True):
            self._pan = None
            self.canvas.get_tk_widget().configure(cursor=CURSOR_DEFAULT)
            self.reset_view()
            return

        if event.button == 1 and self.cfg.get("interaction.pan_with_left_drag", True):
            self._pan = {
                "px": event.x, "py": event.y,
                "xlim": self.ax.get_xlim(), "ylim": self.ax.get_ylim(),
            }
            self.canvas.get_tk_widget().configure(cursor=CURSOR_PAN)

        elif event.button == 3 and self.cfg.get("interaction.zoom_with_right_drag", True):
            self._rubber = {
                "x0": float(event.xdata), "y0": float(event.ydata),
                "px": event.x, "py": event.y,
                "ctrl": self._has_ctrl(event),
            }
            self._rubber_patch.set_visible(True)
            self._rubber_patch.set_xy((event.xdata, event.ydata))
            self._rubber_patch.set_width(0.0)
            self._rubber_patch.set_height(0.0)
            self.canvas.draw_idle()

    # ---------------- 移动 ----------------
    def on_motion(self, event) -> None:
        if self._pan is not None:
            self._do_pan(event)
            return
        if self._rubber is not None:
            self._do_rubber(event)
            return
        self._update_hover(event)

    def _do_pan(self, event) -> None:
        pan = self._pan
        bbox = self.ax.bbox
        if bbox.width <= 0 or bbox.height <= 0:
            return
        x0, x1 = pan["xlim"]
        y0, y1 = pan["ylim"]
        dx = (event.x - pan["px"]) / bbox.width * (x1 - x0)
        dy = (event.y - pan["py"]) / bbox.height * (y1 - y0)
        if not self.lock_x:
            self.ax.set_xlim(x0 - dx, x1 - dx)
        if not self.lock_y:
            self.ax.set_ylim(y0 - dy, y1 - dy)
        self.refresh()

    def _do_rubber(self, event) -> None:
        rub = self._rubber
        if event.xdata is None or event.ydata is None:
            return
        x0, y0 = rub["x0"], rub["y0"]
        x1, y1 = float(event.xdata), float(event.ydata)
        self._rubber_patch.set_xy((min(x0, x1), min(y0, y1)))
        self._rubber_patch.set_width(abs(x1 - x0))
        self._rubber_patch.set_height(abs(y1 - y0))
        self.canvas.draw_idle()

    # ---------------- 松开 ----------------
    def on_release(self, event) -> None:
        if self._pan is not None:
            self._pan = None
            self.canvas.get_tk_widget().configure(cursor=CURSOR_DEFAULT)
            return

        if self._rubber is not None:
            rub = self._rubber
            self._rubber = None
            self._rubber_patch.set_visible(False)
            if event.xdata is None or event.ydata is None:
                self.canvas.draw_idle()
                return
            drag_px = math.hypot(event.x - rub["px"], event.y - rub["py"])
            if drag_px < 4:                      # 只是右键点了一下，忽略
                self.canvas.draw_idle()
                return
            self._apply_zoom(
                rub["x0"], float(event.xdata), rub["y0"], float(event.ydata),
                keep_aspect=rub["ctrl"] and bool(self.cfg.get("interaction.lock_aspect_with_ctrl", True)),
            )
            self.refresh()

    def _apply_zoom(self, xa: float, xb: float, ya: float, yb: float,
                    keep_aspect: bool = False) -> None:
        ax = self.ax
        cur_x = ax.get_xlim()
        cur_y = ax.get_ylim()
        min_span = float(self.cfg.get("interaction.min_span_s", 5e-4))

        dx = abs(xb - xa)
        dy = abs(yb - ya)
        x_ok = dx > min_span
        y_ok = dy > 1e-12
        if not (x_ok or y_ok):
            return

        if keep_aspect and x_ok and y_ok:
            # 等比缩放：两轴采用同一个放大倍数（以框中心为中心），纵横比不变
            scale_x = dx / (cur_x[1] - cur_x[0]) if cur_x[1] != cur_x[0] else 1.0
            scale_y = dy / (cur_y[1] - cur_y[0]) if cur_y[1] != cur_y[0] else 1.0
            scale = max(scale_x, scale_y)
            cx, cy = (xa + xb) / 2.0, (ya + yb) / 2.0
            hw = (cur_x[1] - cur_x[0]) * scale / 2.0
            hh = (cur_y[1] - cur_y[0]) * scale / 2.0
            if not self.lock_x:
                ax.set_xlim(cx - hw, cx + hw)
            else:
                ax.set_xlim(*cur_x)
            if not self.lock_y:
                ax.set_ylim(cy - hh, cy + hh)
            else:
                ax.set_ylim(*cur_y)
            return

        if not x_ok or self.lock_x:
            ax.set_xlim(*cur_x)
        else:
            ax.set_xlim(min(xa, xb), max(xa, xb))
        if not y_ok or self.lock_y:
            ax.set_ylim(*cur_y)
        else:
            ax.set_ylim(min(ya, yb), max(ya, yb))

    # ---------------- 悬浮读数 ----------------
    def _update_hover(self, event) -> None:
        if event.inaxes is not self.ax or event.xdata is None:
            self.hide_hover()
            return
        fs = self.data.fs
        if fs <= 0:
            return
        idx = int(round(event.xdata * fs))
        if idx < 0 or idx >= self.data.n_samples:
            self.hide_hover()
            return

        self._hover_index = idx
        y = float(self.data.y[idx])
        t = idx / fs
        unit = self.data.unit(self.cfg.unit_map())
        prec = int(self.cfg.get("status.precision", 3))
        style = str(self.cfg.get("time_axis.format", "mm:ss.mmm"))
        name = self.data.channel_name or "幅值"
        text = (f"时间 {format_time(t, style)}    {name} {y:.{prec}f}"
                + (f" {unit}" if unit else "") + f"    [第 {idx + 1} 点]")
        self.info_left.configure(text=text)

        show_marker = bool(self.cfg.get("interaction.show_hover_marker", True))
        show_cross = bool(self.cfg.get("interaction.show_crosshair", False))
        self._hover_pt.set_data([t], [y])
        self._hover_pt.set_visible(show_marker)
        self._hover_v.set_xdata([t, t])
        self._hover_v.set_visible(show_cross)
        self._blit_hover()

    def _blit_hover(self) -> None:
        if self._bg is None:
            self.canvas.draw_idle()
            return
        try:
            self.canvas.restore_region(self._bg)
            if self._hover_pt.get_visible():
                self.ax.draw_artist(self._hover_pt)
            if self._hover_v.get_visible():
                self.ax.draw_artist(self._hover_v)
            self.canvas.blit(self.ax.bbox)
        except Exception:
            self.canvas.draw_idle()

    def hide_hover(self) -> None:
        self._hover_index = None
        if not hasattr(self, "_hover_pt"):
            return
        was_visible = self._hover_pt.get_visible() or self._hover_v.get_visible()
        self._hover_pt.set_visible(False)
        self._hover_v.set_visible(False)
        if was_visible and self._bg is not None:
            try:
                self.canvas.restore_region(self._bg)
                self.canvas.blit(self.ax.bbox)
            except Exception:
                self.canvas.draw_idle()
        self.info_left.configure(text="—")

    # ---------------- 键盘 ----------------
    def on_key(self, event) -> None:
        key = event.key
        frac = float(self.cfg.get("interaction.key_pan_fraction", 0.25))
        if key in ("left", "right") and not self.lock_x:
            x0, x1 = self.ax.get_xlim()
            step = (x1 - x0) * frac * (1 if key == "right" else -1)
            self.ax.set_xlim(x0 + step, x1 + step)
            self.refresh()
        elif key in ("a", "A"):
            self.autoscale_y()
        elif key in ("f", "F", "home"):
            self.reset_view()

    # ---------------- 视图命令 ----------------
    def reset_view(self) -> None:
        self.ax.set_xlim(*self._home_xlim)
        self.ax.set_ylim(*self._home_ylim)
        self.refresh()

    def autoscale_y(self) -> None:
        i0, i1 = self._index_range()
        self.ax.set_ylim(*self._calc_ylim(i0, i1))
        self.refresh()

    def zoom_x(self, factor: float) -> None:
        if self.lock_x:
            return
        x0, x1 = self.ax.get_xlim()
        cx = 0.5 * (x0 + x1)
        half = (x1 - x0) * factor * 0.5
        self.ax.set_xlim(cx - half, cx + half)
        self.refresh()

    # ---------------- 配置变更 ----------------
    def apply_config(self) -> None:
        """样式/预处理参数变化后重建整张图（保持当前可视范围）。"""
        cur_x = self.ax.get_xlim()
        cur_y = self.ax.get_ylim()
        self._prepare_axes()
        self.ax.set_xlim(*cur_x)
        self.ax.set_ylim(*cur_y)
        self.refresh()
        self.canvas.draw()

    # ---------------- 导出 ----------------
    def export_png(self, path: str, dpi: Optional[float] = None) -> None:
        """导出当前视图。dpi 与屏幕一致，线宽仍是 1 像素，不会变粗/羽化。"""
        self.fig.savefig(
            path,
            dpi=float(dpi or self.fig.get_dpi()),
            facecolor=self.cfg.get("style.figure_facecolor", "#FFFFFF"),
            edgecolor="none",
        )
