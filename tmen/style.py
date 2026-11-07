"""泰盟 BL 风格的绘图样式。

要点：
* 坐标轴线、网格线、曲线全部按"像素"给线宽：``磅 = 像素 * 72 / dpi``，
  这样屏幕上是 1 像素，``savefig`` 出来的同样是 1 像素，不会变粗、不会出现
  半透明羽化边。
* 默认关闭抗锯齿（``antialiased=False``），保证线条边缘干净锐利。
* 刻度数字默认 ``#1858B8``；坐标轴 ``#404040`` 实线；网格 ``#D2D2D2`` 虚线。
"""

from __future__ import annotations

import math
from typing import List

from matplotlib import rcParams
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import Formatter


def px_to_pt(px: float, dpi: float) -> float:
    """把"像素"换算成 matplotlib 的磅值（1 磅 = 1/72 英寸）。"""
    return max(0.01, float(px) * 72.0 / max(1.0, float(dpi)))


def init_matplotlib(font_family: List[str]) -> None:
    """全局 rcParams（只设置一次）。"""
    rcParams["font.sans-serif"] = font_family + ["DejaVu Sans"]
    rcParams["font.family"] = "sans-serif"
    rcParams["axes.unicode_minus"] = False
    rcParams["savefig.facecolor"] = "auto"
    rcParams["path.simplify"] = False          # 关掉路径简化，避免细节丢失
    rcParams["agg.path.chunksize"] = 20000


# --------------------------------------------------------------------------- #
# 时间格式
# --------------------------------------------------------------------------- #
def format_time(value: float, style: str = "mm:ss.mmm") -> str:
    """把秒数格式化成 ``01:21.131`` 之类的字符串。"""
    if not math.isfinite(value):
        return ""
    sign = "-" if value < 0 else ""
    v = abs(value)
    if style == "seconds":
        return f"{sign}{v:.3f}"
    if style == "ss.mmm":
        return f"{sign}{v:.3f}"

    total_ms = int(round(v * 1000.0))
    minutes, rem = divmod(total_ms, 60000)
    seconds, millis = divmod(rem, 1000)
    if style == "mm:ss":
        return f"{sign}{minutes:02d}:{seconds:02d}"
    return f"{sign}{minutes:02d}:{seconds:02d}.{millis:03d}"


class TimeFormatter(Formatter):
    """横轴刻度：分:秒.毫秒。"""

    def __init__(self, style: str = "mm:ss.mmm") -> None:
        self.style = style

    def set_style(self, style: str) -> None:
        self.style = style

    def __call__(self, x, pos=None):  # noqa: D401 - matplotlib 协议
        try:
            return format_time(float(x), self.style)
        except (TypeError, ValueError):
            return ""


# --------------------------------------------------------------------------- #
# 样式应用
# --------------------------------------------------------------------------- #
def apply_figure_style(fig: Figure, cfg) -> None:
    dpi = float(cfg.get("app.dpi", 100))
    fig.set_dpi(dpi)
    fig.set_facecolor(cfg.get("style.figure_facecolor", "#FFFFFF"))
    sub = cfg.section("subplot")
    try:
        fig.subplots_adjust(
            left=float(sub.get("left", 0.08)),
            right=float(sub.get("right", 0.985)),
            bottom=float(sub.get("bottom", 0.12)),
            top=float(sub.get("top", 0.94)),
            wspace=float(sub.get("wspace", 0.12)),
            hspace=float(sub.get("hspace", 0.12)),
        )
    except (ValueError, TypeError):
        pass


def apply_axes_style(ax: Axes, cfg, xlabel: str, ylabel: str, title: str) -> None:
    """坐标轴、刻度、网格、标签的统一样式。"""
    # 用图形实际 dpi（高 DPI 屏上 matplotlib 会乘上像素比），保证"1 像素"名副其实
    dpi = float(ax.figure.get_dpi())
    axis_color = cfg.get("style.axis_color", "#404040")
    tick_color = cfg.get("style.tick_color", "#404040")
    tick_label_color = cfg.get("style.ticklabel_color", "#1858B8")
    label_color = cfg.get("style.label_color", "#1858B8")

    ax.set_facecolor(cfg.get("style.axes_facecolor", "#FFFFFF"))

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(axis_color)
        spine.set_linewidth(px_to_pt(cfg.get("style.axis_linewidth_px", 1.0), dpi))
        spine.set_zorder(6)

    ax.tick_params(
        axis="both", which="both",
        colors=tick_color,
        labelcolor=tick_label_color,
        length=px_to_pt(cfg.get("style.tick_length_px", 4.0), dpi),
        width=px_to_pt(cfg.get("style.axis_linewidth_px", 1.0), dpi),
        pad=2,
        labelsize=float(cfg.get("style.ticklabel_size", 9.0)),
        direction="out",
    )
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(tick_label_color)
        label.set_fontsize(float(cfg.get("style.ticklabel_size", 9.0)))

    if cfg.get("style.grid_enabled", True):
        ax.set_axisbelow(True)
        ax.grid(
            True,
            color=cfg.get("style.grid_color", "#D2D2D2"),
            linestyle=cfg.get("style.grid_linestyle", "--"),
            linewidth=px_to_pt(cfg.get("style.grid_linewidth_px", 1.0), dpi),
            alpha=1.0,
            zorder=0,
        )
    else:
        ax.grid(False)

    ax.set_xlabel(
        xlabel if cfg.get("style.show_xlabel", True) else "",
        color=label_color,
        fontsize=float(cfg.get("style.label_size", 10.0)),
        labelpad=3,
    )
    ax.set_ylabel(
        ylabel,
        color=label_color,
        fontsize=float(cfg.get("style.label_size", 10.0)),
        labelpad=3,
    )
    ax.set_title(
        title if cfg.get("style.show_title", False) else "",
        color=cfg.get("style.title_color", "#1858B8"),
        fontsize=float(cfg.get("style.title_size", 11.0)),
        pad=4,
    )
    ax.margins(x=0.0, y=0.0)
