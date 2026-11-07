"""``.tmen`` 文件解析。

``.tmen`` 是 OLE2 复合文档（Compound File Binary），内部流：

===============  ====================================================
流名             内容
===============  ====================================================
Channel_Data1    波形本体，float32 小端，无文件头
Config           通道名 / 采样率 / 实验信息（6188 字节定长结构）
Index            设备型号、样本数、记录时间戳
Stimulate        电刺激参数记录（每 44 字节一条）
Event            实验事件标记（每 40 字节一条）
Analysis/Measure 本类实验为空
===============  ====================================================

本模块把这些细节全部封装成 :class:`TmenData`，界面层不再关心字节偏移。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import olefile

# ---- Config 流内的固定偏移 -------------------------------------------------
CFG_SAMPLE_RATE_OFF = 0x46      # float32 采样率
CFG_CHANNEL_NAME_OFF = 0x39A    # UTF-16LE 通道名（张力 / 动脉血压 ...）
CFG_TEXT_OFF = 0x39A            # 其后紧跟实验项目名、实验目的、方法等
# ---- Index 流内的固定偏移 --------------------------------------------------
IDX_DEVICE_OFF = 0x3B8          # UTF-16LE 设备型号 "BL-420N"

# ---- Stimulate 流：44 字节/条 ----------------------------------------------
STIM_RECORD_SIZE = 44
STIM_RECORD_MAGIC = b"\x01\x00\x00\x00\x01\x00\x01\x00"
STIM_MODE_TRAIN = 0x00020000    # 该标志表示"连续/串刺激"，才带频率信息

# ---- Event 流：40 字节/条 ---------------------------------------------------
EVENT_RECORD_SIZE = 40


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class StimulusGroup:
    """一次（一组）电刺激。

    ``Stimulate`` 流里 0.1 s 连续落笔的记录会被合并成一组，
    对应示波器上看到的一段强直/串刺激。
    """

    t0: float                 # 起始时间 (s)
    t1: float                 # 结束时间 (s)
    freq_lo: float            # 频率下限 (Hz)
    freq_hi: float            # 频率上限 (Hz)
    amp_lo: float             # 强度下限 (V)
    amp_hi: float             # 强度上限 (V)
    channel: int              # 刺激通道
    n_records: int            # 组内记录条数

    @property
    def duration(self) -> float:
        return max(0.0, self.t1 - self.t0)

    def amp_text(self) -> str:
        if abs(self.amp_hi - self.amp_lo) < 1e-4:
            return f"{self.amp_lo:.4f}"
        return f"{self.amp_lo:.4f}~{self.amp_hi:.4f}"

    def freq_text(self) -> str:
        if abs(self.freq_hi - self.freq_lo) < 0.05:
            return f"{self.freq_lo:.1f}"
        return f"{self.freq_lo:.1f}~{self.freq_hi:.1f}"

    def label(self, template: str) -> str:
        try:
            return template.format(
                amp=self.amp_text(), freq=self.freq_text(), ch=self.channel
            )
        except Exception:
            return f"{self.amp_text()}V {self.freq_text()}Hz {self.channel}c"


@dataclass
class EventMark:
    """Event 流中的一条标记。"""

    index: int
    time: float
    value: float
    kind: int


@dataclass
class TmenData:
    """一个 ``.tmen`` 文件解析后的全部内容。"""

    path: Path
    fs: float
    raw: np.ndarray                       # 原始采样值（float64）
    y: np.ndarray                         # 预处理后（去零点/平滑）用于绘图
    t: np.ndarray                         # 时间轴 (s)
    channel_name: str = ""
    experiment: str = ""
    device: str = ""
    n_samples: int = 0
    offset_applied: float = 0.0
    zero_mode_used: str = "none"
    stimuli: List[StimulusGroup] = field(default_factory=list)
    events: List[EventMark] = field(default_factory=list)
    streams: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.n_samples / self.fs if self.fs > 0 else 0.0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    def unit(self, mapping: Dict[str, str]) -> str:
        return mapping.get(self.channel_name, "")

    def ylabel(self, mapping: Dict[str, str]) -> str:
        unit = self.unit(mapping)
        if self.channel_name and unit:
            return f"{self.channel_name} ({unit})"
        return self.channel_name or unit or "幅值"


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def _read_wide_string(buf: bytes, offset: int) -> Tuple[str, int]:
    """从 ``offset`` 读一个 UTF-16LE 字符串，返回 (文本, 下一个偏移)。"""
    n = len(buf)
    if offset < 0 or offset >= n - 1:
        return "", offset
    end = offset
    while end < n - 1 and not (buf[end] == 0 and buf[end + 1] == 0):
        end += 2
    text = buf[offset:end].decode("utf-16le", errors="replace")
    text = "".join(ch for ch in text if ch >= " " or ch in "\n\t")
    return text.strip(), end + 2


def _snap_rate(fs: float, enabled: bool) -> float:
    """200.00389 → 200：设备把 5 ms 采样间隔写成浮点，取整更好看。"""
    if not enabled or fs <= 0:
        return fs
    nearest = round(fs)
    if nearest > 0 and abs(fs - nearest) / nearest < 0.002:
        return float(nearest)
    return fs


def _detect_record_stride(data: bytes, default: int) -> int:
    """用记录头出现位置的最小公倍数式间隔推断记录长度。"""
    positions: List[int] = []
    start = data.find(STIM_RECORD_MAGIC)
    while start >= 0 and len(positions) < 200:
        positions.append(start)
        start = data.find(STIM_RECORD_MAGIC, start + 1)
    if len(positions) < 3:
        return default
    diffs = [b - a for a, b in zip(positions, positions[1:]) if b > a]
    if not diffs:
        return default
    values, counts = np.unique(np.array(diffs), return_counts=True)
    stride = int(values[int(np.argmax(counts))])
    return stride if 16 <= stride <= 256 else default


# --------------------------------------------------------------------------- #
# 各流解析
# --------------------------------------------------------------------------- #
def _parse_config(cfg_bytes: bytes) -> Dict[str, Any]:
    out: Dict[str, Any] = {"fs": None, "channel_name": "", "experiment": ""}
    if len(cfg_bytes) >= CFG_SAMPLE_RATE_OFF + 4:
        try:
            fs = struct.unpack_from("<f", cfg_bytes, CFG_SAMPLE_RATE_OFF)[0]
            if np.isfinite(fs) and 0.1 < fs < 1e6:
                out["fs"] = float(fs)
        except struct.error:
            pass
    if len(cfg_bytes) > CFG_CHANNEL_NAME_OFF:
        name, nxt = _read_wide_string(cfg_bytes, CFG_CHANNEL_NAME_OFF)
        if name:
            out["channel_name"] = name[:24]
        title, _ = _read_wide_string(cfg_bytes, nxt)
        if title:
            out["experiment"] = title[:60]
    return out


def _parse_index(idx_bytes: bytes) -> Dict[str, Any]:
    out: Dict[str, Any] = {"device": "", "n_samples": None, "start": None}
    if len(idx_bytes) > IDX_DEVICE_OFF + 32:
        device, _ = _read_wide_string(idx_bytes, IDX_DEVICE_OFF)
        out["device"] = device[:24]
    if len(idx_bytes) >= 0x40:
        try:
            n, = struct.unpack_from("<Q", idx_bytes, 0x38)
            if 0 < n < 2 ** 31:
                out["n_samples"] = int(n)
            t0, = struct.unpack_from("<Q", idx_bytes, 0x28)
            if 0 < t0 < 2 ** 32:
                out["start"] = int(t0)
        except struct.error:
            pass
    return out


def _parse_stimulate(stim_bytes: bytes, fs: float, n_samples: int,
                     merge_gap_s: float, min_freq: float, max_freq: float,
                     max_amp: float) -> Tuple[List[StimulusGroup], List[str]]:
    """解析电刺激记录并合并成"组"。"""
    notes: List[str] = []
    if len(stim_bytes) < STIM_RECORD_SIZE:
        return [], notes

    stride = _detect_record_stride(stim_bytes, STIM_RECORD_SIZE)
    raw_events: List[Tuple[float, float, float, int]] = []  # t, freq, amp, ch

    for off in range(0, len(stim_bytes) - stride + 1, stride):
        rec = stim_bytes[off:off + STIM_RECORD_SIZE]
        try:
            kind, = struct.unpack_from("<i", rec, 0)
            if kind != 1:
                continue
            channel, flag = struct.unpack_from("<hh", rec, 4)
            mode, = struct.unpack_from("<i", rec, 8)
            freq, = struct.unpack_from("<f", rec, 28)
            amp, = struct.unpack_from("<f", rec, 32)
            idx, = struct.unpack_from("<i", rec, 40)
        except struct.error:
            continue

        if mode != STIM_MODE_TRAIN:       # 单刺激/参数快照，没有频率信息
            continue
        if not (min_freq <= freq <= max_freq):
            continue
        if not (0.0 < amp <= max_amp):
            continue
        if not (0 <= idx <= n_samples * 1.05 + 1):
            continue
        raw_events.append((idx / fs, float(freq), float(amp), int(channel)))

    if not raw_events:
        return [], notes

    raw_events.sort(key=lambda e: e[0])

    # 合并：通道相同、频率/强度连续、时间间隔不超过 merge_gap_s
    groups: List[Dict[str, Any]] = []
    for t, freq, amp, ch in raw_events:
        cur = groups[-1] if groups else None
        mergeable = (
            cur is not None
            and cur["ch"] == ch
            and abs(freq - cur["freq_hi"]) <= max(0.6, 0.015 * cur["freq_hi"])
            and abs(amp - cur["amp_hi"]) <= max(0.003, 0.003 * cur["amp_hi"])
            and (t - cur["t1"]) <= merge_gap_s
        )
        if mergeable:
            cur["t1"] = t
            cur["freq_hi"] = max(cur["freq_hi"], freq)
            cur["freq_lo"] = min(cur["freq_lo"], freq)
            cur["amp_hi"] = max(cur["amp_hi"], amp)
            cur["amp_lo"] = min(cur["amp_lo"], amp)
            cur["n"] += 1
        else:
            groups.append({
                "t0": t, "t1": t, "freq_lo": freq, "freq_hi": freq,
                "amp_lo": amp, "amp_hi": amp, "ch": ch, "n": 1,
            })

    out = [
        StimulusGroup(
            t0=g["t0"], t1=g["t1"],
            freq_lo=g["freq_lo"], freq_hi=g["freq_hi"],
            amp_lo=g["amp_lo"], amp_hi=g["amp_hi"],
            channel=g["ch"], n_records=g["n"],
        )
        for g in groups
    ]
    if len(out) > 200:
        notes.append(f"刺激组较多（{len(out)} 组），标注文字将按间距自动抽稀")
    return out, notes


def _parse_event(ev_bytes: bytes, fs: float, n_samples: int) -> List[EventMark]:
    out: List[EventMark] = []
    if len(ev_bytes) < EVENT_RECORD_SIZE:
        return out
    for off in range(0, len(ev_bytes) - EVENT_RECORD_SIZE + 1, EVENT_RECORD_SIZE):
        rec = ev_bytes[off:off + EVENT_RECORD_SIZE]
        try:
            tag, = struct.unpack_from("<i", rec, 0)
            value, = struct.unpack_from("<f", rec, 8)
            idx, = struct.unpack_from("<i", rec, 16)
        except struct.error:
            continue
        kind = (tag >> 16) & 0xFFFF
        if kind not in (10, 13):
            continue
        if not (0 <= idx <= n_samples * 1.05 + 1):
            continue
        if not np.isfinite(value) or abs(value) > 1e6:
            continue
        out.append(EventMark(index=int(idx), time=idx / fs,
                             value=float(value), kind=int(kind)))
    return out


# --------------------------------------------------------------------------- #
# 预处理
# --------------------------------------------------------------------------- #
def _apply_zero(y: np.ndarray, mode: str, points: int,
                channel: str, auto_channels: Sequence[str]) -> Tuple[np.ndarray, float, str]:
    """零点校正。血压这类绝对量默认不校正，张力这类相对量默认校正。"""
    if channel and channel in auto_channels:
        auto_mode = "first"
    else:
        auto_mode = "none"

    mode = (mode or "auto").lower()
    if mode == "auto":
        mode = auto_mode

    if mode == "none" or y.size == 0:
        return y, 0.0, "none"

    n = max(1, min(int(points), y.size))
    head = y[:n]
    head = head[np.isfinite(head)]
    if head.size == 0:
        return y, 0.0, "none"

    if mode == "first":
        offset = float(np.mean(head))
    elif mode == "median":
        offset = float(np.median(head))
    elif mode == "min":
        offset = float(np.nanmin(y))
    else:
        return y, 0.0, "none"
    return y - offset, offset, mode


def _smooth(y: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or y.size < window:
        return y
    kernel = np.ones(int(window), dtype=np.float64) / float(window)
    return np.convolve(y, kernel, mode="same")


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def read_tmen(path: str | Path, cfg) -> TmenData:
    """读取一个 ``.tmen`` 文件。``cfg`` 为 :class:`tmen.config.Config`。"""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    if not olefile.isOleFile(str(path)):
        raise ValueError("不是有效的 .tmen（OLE2）复合文档")

    notes: List[str] = []
    ole = olefile.OleFileIO(str(path))
    try:
        streams = [e[-1] for e in ole.listdir(streams=True)]
        stream_name = str(cfg.get("data.stream_name", "Channel_Data1"))
        if not ole.exists(stream_name):
            candidates = sorted(s for s in streams if s.startswith("Channel_Data"))
            if not candidates:
                raise ValueError(
                    "文件里没有 Channel_Data 数据流，可能不是泰盟 BL 数据。\n"
                    f"实际流：{', '.join(streams) or '（空）'}"
                )
            stream_name = candidates[0]
            notes.append(f"已自动改用数据流 {stream_name}")

        raw_bytes = ole.openstream(stream_name).read()
        cfg_bytes = ole.openstream("Config").read() if ole.exists("Config") else b""
        idx_bytes = ole.openstream("Index").read() if ole.exists("Index") else b""
        stim_bytes = ole.openstream("Stimulate").read() if ole.exists("Stimulate") else b""
        ev_bytes = ole.openstream("Event").read() if ole.exists("Event") else b""
    finally:
        ole.close()

    usable = len(raw_bytes) - (len(raw_bytes) % 4)
    if usable <= 0:
        raise ValueError("数据流为空")
    if usable != len(raw_bytes):
        notes.append("数据流长度不是 4 的倍数，已截断尾部残字节")

    raw = np.frombuffer(raw_bytes[:usable], dtype="<f4").astype(np.float64)

    cfg_info = _parse_config(cfg_bytes)
    idx_info = _parse_index(idx_bytes)

    fs = cfg_info.get("fs") or float(cfg.get("data.sample_rate_fallback", 1000.0))
    fs = _snap_rate(float(fs), bool(cfg.get("data.snap_sample_rate", True)))

    n_samples = raw.size
    if idx_info.get("n_samples") and idx_info["n_samples"] != n_samples:
        notes.append(
            f"Index 记录 {idx_info['n_samples']} 点，实际 {n_samples} 点（文件可能被截断）"
        )

    bad = int(np.count_nonzero(~np.isfinite(raw)))
    if bad:
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
        notes.append(f"修正 {bad} 个非法数值（NaN/Inf）")

    channel = cfg_info.get("channel_name", "")
    data = TmenData(
        path=path,
        fs=fs,
        raw=raw,
        y=raw,
        t=np.arange(n_samples, dtype=np.float64) / fs if fs > 0 else np.arange(n_samples, dtype=np.float64),
        channel_name=channel,
        experiment=cfg_info.get("experiment", ""),
        device=idx_info.get("device", ""),
        n_samples=n_samples,
        streams=streams,
        notes=notes,
    )

    zeroed, offset, used = _apply_zero(
        raw,
        str(cfg.get("data.zero_mode", "auto")),
        int(cfg.get("data.zero_points", 2000)),
        channel,
        cfg.auto_zero_channels(),
    )
    data.offset_applied = offset
    data.zero_mode_used = used
    data.y = _smooth(zeroed, int(cfg.get("data.smooth_window", 1)))

    if cfg.get("stimulus.enabled", True) and stim_bytes:
        data.stimuli, stim_notes = _parse_stimulate(
            stim_bytes, fs, n_samples,
            float(cfg.get("stimulus.merge_gap_s", 0.25)),
            float(cfg.get("stimulus.min_freq_hz", 0.5)),
            float(cfg.get("stimulus.max_freq_hz", 100000.0)),
            float(cfg.get("stimulus.max_amp_v", 200.0)),
        )
        data.notes.extend(stim_notes)
    data.events = _parse_event(ev_bytes, fs, n_samples)
    return data
