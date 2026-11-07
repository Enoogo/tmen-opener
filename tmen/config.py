"""配置管理。

全部可调参数集中在 ``config.json`` 中，本模块负责：

* 定义默认值与字段元信息（中文名称、类型、取值范围）；
* 读写 ``config.json``；
* 以 ``"section.key"`` 形式访问任意一项；
* 为设置界面提供字段清单（设置界面完全由 FIELD_TABLE 自动生成，
  因此配置文件里新增一项，设置界面就自动多一个控件）。

配置项分节：
    app        窗口 / 标签页 / 绘图点密度
    data       数据流、采样率、平滑、零点校正
    style      颜色、线宽、字体、网格
    time_axis  横轴（分:秒.毫秒）
    y_axis     纵轴数字格式
    interaction 鼠标缩放 / 拖动 / 锁定
    stimulus   电刺激标注
    events     事件标记
    status     底部读数精度
    subplot    子图边距（Subplot configuration tool 的默认值）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# --------------------------------------------------------------------------- #
# 字段定义表： (键, 中文名, 默认值, 控件类型, 额外信息)
#   控件类型: bool / int / float / str / color / choice / text
#   额外信息: choice 时是候选值列表, int/float 时是 (min, max, step)
# 顺序即设置界面的显示顺序。
# --------------------------------------------------------------------------- #
Field = Tuple[str, str, Any, str, Any]

FIELD_TABLE: List[Tuple[str, str, List[Field]]] = [
    ("app", "窗口与标签页", [
        ("title", "窗口标题", "泰盟 BL .tmen 波形查看器", "str", None),
        ("window_width", "窗口宽度 (px)", 1280, "int", (640, 4096, 20)),
        ("window_height", "窗口高度 (px)", 800, "int", (480, 3000, 20)),
        ("dpi", "绘图 DPI", 100, "int", (72, 300, 1)),
        ("remember_geometry", "记住窗口大小", True, "bool", None),
        ("max_points_per_curve", "降采样目标点数", 4000, "int", (500, 40000, 100)),
        ("confirm_close_tab", "关闭标签页时确认", False, "bool", None),
    ]),
    ("data", "数据与预处理", [
        ("stream_name", "数据流名称", "Channel_Data1", "str", None),
        ("sample_rate_fallback", "采样率回退值 (Hz)", 1000.0, "float", (0.1, 1000000, 1)),
        ("snap_sample_rate", "采样率取整 (200.0039→200)", True, "bool", None),
        ("smooth_window", "平滑窗口 (1=不平滑)", 1, "int", (1, 501, 2)),
        ("zero_mode", "零点校正", "auto", "choice",
         ["auto", "none", "first", "median", "min"]),
        ("zero_points", "零点计算点数", 2000, "int", (10, 100000, 100)),
        ("zero_auto_channels", "自动校零通道名", "张力,肌张力,force,Force", "str", None),
        ("channel_units", "通道单位表", "张力=g;肌张力=g;动脉血压=mmHg;血压=mmHg", "str", None),
    ]),
    ("style", "配色与线型", [
        ("figure_facecolor", "画布背景色", "#FFFFFF", "color", None),
        ("axes_facecolor", "绘图区背景色", "#FFFFFF", "color", None),
        ("waveform_color", "波形颜色", "#D0021B", "color", None),
        ("waveform_linewidth_px", "波形线宽 (像素)", 1.0, "float", (0.5, 6.0, 0.5)),
        ("antialiased", "抗锯齿 (关闭=纯单像素)", False, "bool", None),
        ("axis_color", "坐标轴颜色", "#404040", "color", None),
        ("axis_linewidth_px", "坐标轴线宽 (像素)", 1.0, "float", (0.5, 6.0, 0.5)),
        ("tick_color", "刻度线颜色", "#404040", "color", None),
        ("tick_length_px", "刻度长度 (像素)", 4.0, "float", (0.0, 20.0, 0.5)),
        ("grid_enabled", "显示网格", True, "bool", None),
        ("grid_color", "网格颜色", "#D2D2D2", "color", None),
        ("grid_linewidth_px", "网格线宽 (像素)", 1.0, "float", (0.5, 4.0, 0.5)),
        ("grid_linestyle", "网格线型", "--", "choice", ["--", ":", "-.", "-"]),
        ("ticklabel_color", "刻度数字颜色", "#1858B8", "color", None),
        ("ticklabel_size", "刻度字号", 9.0, "float", (4.0, 30.0, 0.5)),
        ("label_color", "轴标题颜色", "#1858B8", "color", None),
        ("label_size", "轴标题字号", 10.0, "float", (4.0, 30.0, 0.5)),
        ("show_xlabel", "显示横轴标题", True, "bool", None),
        ("xlabel", "横轴标题文字", "时间", "str", None),
        ("ylabel_mode", "纵轴标题", "channel", "choice", ["channel", "custom", "none"]),
        ("ylabel_custom", "自定义纵轴标题", "", "str", None),
        ("show_title", "显示图表标题", False, "bool", None),
        ("title_template", "标题模板", "{name}", "str", None),
        ("title_color", "标题颜色", "#1858B8", "color", None),
        ("title_size", "标题字号", 11.0, "float", (4.0, 32.0, 0.5)),
        ("font_family", "字体列表 (靠前优先)",
         "Microsoft YaHei,SimHei,WenQuanYi Zen Hei,Noto Sans CJK SC,DejaVu Sans", "str", None),
    ]),
    ("time_axis", "横轴时间格式", [
        ("format", "显示格式", "mm:ss.mmm", "choice",
         ["mm:ss.mmm", "mm:ss", "ss.mmm", "seconds"]),
        ("right_pad_ratio", "右端留白比例", 0.02, "float", (0.0, 0.3, 0.002)),
        ("show_hint", "坐标轴角标提示", False, "bool", None),
    ]),
    ("y_axis", "纵轴数字格式", [
        ("format", "数字格式", "%.2f", "choice",
         ["%.0f", "%.1f", "%.2f", "%.3f", "%.4f", "%g"]),
        ("autoscale_padding", "自适应留白比例", 0.06, "float", (0.0, 0.5, 0.01)),
    ]),
    ("interaction", "鼠标交互", [
        ("wheel_zoom_x", "滚轮缩放横轴", True, "bool", None),
        ("ctrl_wheel_zoom_y", "Ctrl+滚轮缩放纵轴", True, "bool", None),
        ("wheel_zoom_factor", "每格缩放系数", 0.85, "float", (0.5, 0.99, 0.01)),
        ("pan_with_left_drag", "左键拖动=平移", True, "bool", None),
        ("zoom_with_right_drag", "右键拖动=框选缩放", True, "bool", None),
        ("lock_aspect_with_ctrl", "Ctrl=锁定纵横比", True, "bool", None),
        ("double_click_reset", "双击复位全图", True, "bool", None),
        ("show_hover_marker", "显示悬浮点标记", True, "bool", None),
        ("show_crosshair", "显示悬浮十字线", False, "bool", None),
        ("key_pan_fraction", "方向键平移比例", 0.25, "float", (0.02, 1.0, 0.01)),
        ("min_span_s", "最小可视跨度 (s)", 0.0005, "float", (1e-6, 1.0, 0.0001)),
    ]),
    ("stimulus", "电刺激标注", [
        ("enabled", "解析并标注刺激", True, "bool", None),
        ("show_marker", "绘制刺激竖线", True, "bool", None),
        ("show_band", "绘制刺激区间色带", True, "bool", None),
        ("marker_color", "竖线颜色", "#E08A00", "color", None),
        ("marker_linewidth_px", "竖线线宽 (像素)", 1.0, "float", (0.5, 4.0, 0.5)),
        ("marker_linestyle", "竖线线型", "--", "choice", ["--", ":", "-.", "-"]),
        ("band_color", "色带颜色", "#F5C043", "color", None),
        ("band_alpha", "色带透明度", 0.20, "float", (0.0, 1.0, 0.05)),
        ("label_template", "标注文字模板", "{amp}V {freq}Hz {ch}c", "str", None),
        ("label_color", "标注文字颜色", "#A86400", "color", None),
        ("label_size", "标注文字字号", 8.0, "float", (4.0, 24.0, 0.5)),
        ("label_min_gap_px", "标注最小间距 (px)", 32, "int", (0, 2000, 8)),
        ("label_rows", "标注最多行数", 3, "int", (1, 8, 1)),
        ("label_row_step", "行间距 (轴高比例)", 0.048, "float", (0.01, 0.2, 0.004)),
        ("merge_gap_s", "同组最大间隔 (s)", 0.25, "float", (0.0, 10.0, 0.05)),
        ("min_freq_hz", "有效频率下限 (Hz)", 0.5, "float", (0.0, 1000.0, 0.1)),
        ("max_freq_hz", "有效频率上限 (Hz)", 100000.0, "float", (1.0, 1e7, 100.0)),
        ("max_amp_v", "有效强度上限 (V)", 200.0, "float", (0.0, 1e4, 1.0)),
    ]),
    ("events", "事件标记 (Event 流)", [
        ("enabled", "显示事件标记", False, "bool", None),
        ("color", "标记颜色", "#7A7A7A", "color", None),
        ("size", "标记字号", 7.0, "float", (4.0, 20.0, 0.5)),
        ("label_template", "文字模板", "{value:g}", "str", None),
    ]),
    ("status", "底部读数", [
        ("show_peak_to_peak", "显示峰峰值", True, "bool", None),
        ("show_min_max", "显示最大/最小值", True, "bool", None),
        ("precision", "小数位数", 3, "int", (0, 8, 1)),
    ]),
    ("subplot", "子图边距", [
        ("left", "左边距", 0.088, "float", (0.0, 0.95, 0.005)),
        ("right", "右边距", 0.975, "float", (0.05, 1.0, 0.005)),
        ("bottom", "下边距", 0.125, "float", (0.0, 0.95, 0.005)),
        ("top", "上边距", 0.940, "float", (0.05, 1.0, 0.005)),
        ("wspace", "水平间距", 0.120, "float", (0.0, 1.0, 0.01)),
        ("hspace", "垂直间距", 0.120, "float", (0.0, 1.0, 0.01)),
    ]),
]


def build_defaults() -> Dict[str, Dict[str, Any]]:
    """由 FIELD_TABLE 生成默认配置字典。"""
    out: Dict[str, Dict[str, Any]] = {}
    for section, _label, fields in FIELD_TABLE:
        out[section] = {key: default for key, _n, default, _t, _e in fields}
    return out


def fields_of(section: str) -> List[Field]:
    for name, _label, fields in FIELD_TABLE:
        if name == section:
            return fields
    return []


def section_label(section: str) -> str:
    for name, label, _fields in FIELD_TABLE:
        if name == section:
            return label
    return section


def app_dir() -> Path:
    """程序所在目录（兼容 PyInstaller 打包后的 exe）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return app_dir() / "config.json"


class Config:
    """嵌套字典形式的配置，支持 "section.key" 读写。"""

    def __init__(self, data: Dict[str, Any] | None = None,
                 path: Path | None = None) -> None:
        self.path = Path(path) if path else config_path()
        self.data: Dict[str, Any] = build_defaults()
        self.dirty = False
        if data:
            self._merge(data)

    # ---------------- 读写 ----------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        cfg = cls(path=path)
        try:
            if cfg.path.is_file():
                raw = json.loads(cfg.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    cfg._merge(raw)
                cfg.dirty = False
        except Exception:  # 配置损坏时静默回退到默认值
            cfg.data = build_defaults()
        return cfg

    def save(self) -> Path:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.dirty = False
        return self.path

    def reset(self) -> None:
        self.data = build_defaults()
        self.dirty = True

    def _merge(self, raw: Dict[str, Any]) -> None:
        """只接受已知字段，缺失项用默认值补齐（兼容旧版配置文件）。"""
        defaults = build_defaults()
        for section, values in defaults.items():
            incoming = raw.get(section)
            if isinstance(incoming, dict):
                for key, default in values.items():
                    if key in incoming:
                        self.data[section][key] = self._coerce(
                            incoming[key], default
                        )
        # 保留用户手工添加的未知字段，避免丢失
        for section, values in raw.items():
            if isinstance(values, dict):
                target = self.data.setdefault(section, {})
                for key, value in values.items():
                    target.setdefault(key, value)

    @staticmethod
    def _coerce(value: Any, default: Any) -> Any:
        try:
            if isinstance(default, bool):
                return bool(value)
            if isinstance(default, int):
                return int(round(float(value)))
            if isinstance(default, float):
                return float(value)
            if isinstance(default, str):
                return str(value)
        except (TypeError, ValueError):
            return default
        return value

    # ---------------- 访问 ----------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self.dirty = True

    def section(self, name: str) -> Dict[str, Any]:
        return self.data.get(name, {})

    # ---------------- 派生配置 ----------------
    def font_list(self) -> List[str]:
        raw = str(self.get("style.font_family", ""))
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]

    def unit_map(self) -> Dict[str, str]:
        raw = str(self.get("data.channel_units", ""))
        out: Dict[str, str] = {}
        for chunk in raw.replace(",", ";").split(";"):
            if "=" in chunk:
                key, val = chunk.split("=", 1)
                out[key.strip()] = val.strip()
        return out

    def auto_zero_channels(self) -> List[str]:
        raw = str(self.get("data.zero_auto_channels", ""))
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]

    def copy_data(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self.data))
