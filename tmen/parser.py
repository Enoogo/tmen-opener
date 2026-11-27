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
CFG_TEXT_FIELDS = {
    "实验项目": (0x400, 0x100),
    "实验目的": (0x500, 0x100),
    "实验原理": (0x700, 0x200),
    "实验对象": (0x900, 0x100),
    "器材": (0xA00, 0x100),
    "药品与试剂": (0xB00, 0x100),
    "实验步骤": (0xC00, 0x800),
    "注意事项": (0x1400, 0x200),
    "思考题": (0x1600, 0x200),
}
# ---- Index 流内的固定偏移 --------------------------------------------------
IDX_DEVICE_OFF = 0x00          # UTF-16LE 设备型号 "BL-420N"
IDX_DEVICE_ASCII_OFF = 0x3B8   # 同一型号的 ASCII 副本
IDX_EXPERIMENT_OFF = 0x4C

# ---- Stimulate 流：44 字节/条 ----------------------------------------------
STIM_RECORD = struct.Struct("<ihhii5fii")
STIM_MODE_PULSE = 0
STIM_MODE_TRAIN = 0x00020000

# ---- Event 流：40 字节/条 ---------------------------------------------------
EVENT_RECORD_SIZE = 40
DEFAULT_STIMULUS_LABEL = "{amp}V, {frequency}, {ch}c"


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class StimulusRecord:
    """Stimulate 流中的一条已识别记录，保留原始参数和采样点位置。"""

    index: int
    time: float
    channel: int
    mode: int
    kind: int
    flag: int
    count: int
    parameter_16: float
    pulse_width_ms: float
    interval_ms: float
    frequency_hz: float
    amplitude_v: float
    parameter_36: int


@dataclass
class UnparsedRecord:
    stream: str
    offset: int
    raw: bytes
    reason: str
    index: int | None = None


@dataclass
class StimulusGroup:
    """一次电刺激或一段连续刺激，单条记录仍可追溯。"""

    t0: float                 # 起始时间 (s)
    t1: float                 # 结束时间 (s)
    freq_lo: float | None     # 频率下限 (Hz)
    freq_hi: float | None     # 频率上限 (Hz)
    amp_lo: float             # 强度下限 (V)
    amp_hi: float             # 强度上限 (V)
    channel: int              # 刺激通道
    n_records: int            # 组内记录条数
    records: List[StimulusRecord] = field(default_factory=list)
    frequency_estimated: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.t1 - self.t0)

    def amp_text(self) -> str:
        if abs(self.amp_hi - self.amp_lo) < 1e-4:
            return f"{self.amp_lo:.3f}"
        return f"{self.amp_lo:.3f}~{self.amp_hi:.3f}"

    def freq_text(self) -> str:
        if self.freq_lo is None or self.freq_hi is None:
            return "—"
        if self.frequency_estimated:
            return f"≈{self.freq_lo:.1f}"
        if abs(self.freq_hi - self.freq_lo) < 0.05:
            return f"{self.freq_lo:.1f}"
        return f"{self.freq_lo:.1f}~{self.freq_hi:.1f}"

    def label(self, template: str) -> str:
        freq = self.freq_text()
        frequency = f"{freq}Hz" if self.freq_lo is not None else (
            "单次" if self.n_records == 1 else "频率未记录"
        )
        try:
            return template.format(
                amp=self.amp_text(), freq=freq, frequency=frequency, ch=self.channel
            )
        except (KeyError, IndexError, ValueError, AttributeError):
            return f"{self.amp_text()}V, {frequency}, {self.channel}c"


@dataclass
class EventMark:
    """Event 流中的一条标记。"""

    index: int
    time: float
    value: float
    kind: int
    timestamp: int | None = None


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
    recorded_sample_rate: float | None = None
    start_timestamp: int | None = None
    end_timestamp: int | None = None
    experiment_details: Dict[str, str] = field(default_factory=dict)
    stimulus_records: List[StimulusRecord] = field(default_factory=list)
    unparsed_records: List[UnparsedRecord] = field(default_factory=list)
    raw_metadata: Dict[str, bytes] = field(default_factory=dict)

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


# --------------------------------------------------------------------------- #
# 各流解析
# --------------------------------------------------------------------------- #
def _parse_config(cfg_bytes: bytes) -> Dict[str, Any]:
    details = {}
    fs = None
    if len(cfg_bytes) >= CFG_SAMPLE_RATE_OFF + 4:
        rate, = struct.unpack_from("<f", cfg_bytes, CFG_SAMPLE_RATE_OFF)
        if 0.1 < rate < 1e6:
            fs = rate
    channel, _ = _read_wide_string(cfg_bytes, CFG_CHANNEL_NAME_OFF)
    for name, (offset, size) in CFG_TEXT_FIELDS.items():
        value, _ = _read_wide_string(cfg_bytes[offset:offset + size], 0)
        if value:
            details[name] = value
    return {"fs": fs, "channel_name": channel, "details": details}


def _parse_index(idx_bytes: bytes) -> Dict[str, Any]:
    device, _ = _read_wide_string(idx_bytes[:0x20], IDX_DEVICE_OFF)
    if not device.isascii() or not device:
        model = idx_bytes[IDX_DEVICE_ASCII_OFF:IDX_DEVICE_ASCII_OFF + 16]
        device = model.split(b"\0", 1)[0].decode("ascii", errors="replace")
    experiment, _ = _read_wide_string(idx_bytes[:0x14C], IDX_EXPERIMENT_OFF)
    out: Dict[str, Any] = {"device": device, "experiment": experiment}
    if len(idx_bytes) >= 0x40:
        start, end, n = struct.unpack_from("<3Q", idx_bytes, 0x28)
        if 0 < n < 2 ** 31:
            out["n_samples"] = n
        if 0 < start < 2 ** 32:
            out["start"] = start
        if 0 < end < 2 ** 32:
            out["end"] = end
    return out


def _same_stimulus(record: StimulusRecord, previous: StimulusRecord,
                   fs: float, merge_gap_s: float) -> bool:
    if record.channel != previous.channel or record.mode != previous.mode:
        return False
    if (record.parameter_16, record.pulse_width_ms) != (
        previous.parameter_16, previous.pulse_width_ms
    ):
        return False
    gap_samples = record.index - previous.index
    if gap_samples < 0:
        return False
    if record.mode == STIM_MODE_PULSE:
        return (gap_samples <= merge_gap_s * fs
                and record.amplitude_v == previous.amplitude_v
                and record.frequency_hz == previous.frequency_hz)

    freq, amp = previous.frequency_hz, previous.amplitude_v
    max_gap_samples = merge_gap_s * fs
    if record.kind == 0:
        # 低频串刺激的后续脉冲间隔可能大于用户设置的合并间隔。
        max_gap_samples = max(max_gap_samples, fs / freq + 1)
    elif previous.kind == 0:
        return False  # 前一串已记录后续脉冲，此处出现新的起点
    return (gap_samples <= max_gap_samples
            and abs(record.frequency_hz - freq) <= max(0.6, 0.015 * freq)
            and abs(record.amplitude_v - amp) <= max(0.003, 0.003 * amp))


def _make_stimulus_group(records: List[StimulusRecord], fs: float) -> StimulusGroup:
    first, last = records[0], records[-1]
    frequencies = [record.frequency_hz for record in records if record.frequency_hz > 0]
    estimated = False
    if not frequencies and len(records) >= 3:
        steps = [b.index - a.index for a, b in zip(records, records[1:])]
        if min(steps) > 0 and max(steps) - min(steps) <= 1:
            frequencies = [fs * len(steps) / (last.index - first.index)]
            estimated = True
    amplitudes = [record.amplitude_v for record in records]
    return StimulusGroup(
        first.time, last.time, min(frequencies, default=None), max(frequencies, default=None),
        min(amplitudes), max(amplitudes), first.channel, len(records), records, estimated,
    )


def _parse_stimulate(stim_bytes: bytes, fs: float, n_samples: int,
                     merge_gap_s: float, min_freq: float, max_freq: float,
                     max_amp: float, unparsed: List[UnparsedRecord],
                     ) -> Tuple[List[StimulusRecord], List[StimulusGroup]]:
    records: List[StimulusRecord] = []
    groups: List[StimulusGroup] = []
    current: List[StimulusRecord] = []
    size = STIM_RECORD.size
    usable = len(stim_bytes) // size * size
    for off in range(0, usable, size):
        kind, ch, flag, mode, count, p16, width, interval, freq, amp, p36, idx = (
            STIM_RECORD.unpack_from(stim_bytes, off)
        )
        index_ok = 0 <= idx <= n_samples
        reason = ""
        if not (mode == STIM_MODE_TRAIN and kind in (0, 1)
                or mode == STIM_MODE_PULSE and kind == 1):
            reason = f"未知记录类型 {kind} / 模式 0x{mode & 0xFFFFFFFF:08X}"
        elif not index_ok:
            reason = "采样点超出波形范围"
        elif ch <= 0 or not np.isfinite([p16, width, interval, freq, amp]).all():
            reason = "通道或参数无效"
        elif not 0 <= amp <= max_amp or (
            (freq != 0 or mode == STIM_MODE_TRAIN) and not (0 < freq and min_freq <= freq <= max_freq)
        ):
            reason = "强度或频率超出设定范围"

        if reason:
            unparsed.append(UnparsedRecord(
                "Stimulate", off, stim_bytes[off:off + size], reason, idx if index_ok else None,
            ))
            if current:
                groups.append(_make_stimulus_group(current, fs))
                current = []
            continue

        record = StimulusRecord(idx, idx / fs, ch, mode, kind, flag, count,
                                p16, width, interval, freq, amp, p36)
        records.append(record)
        if current and not _same_stimulus(record, current[-1], fs, merge_gap_s):
            groups.append(_make_stimulus_group(current, fs))
            current = []
        current.append(record)

    if current:
        groups.append(_make_stimulus_group(current, fs))
    if usable < len(stim_bytes):
        unparsed.append(UnparsedRecord("Stimulate", usable, stim_bytes[usable:], "记录尾部不完整"))
    return records, sorted(groups, key=lambda group: group.t0)


def _parse_event(ev_bytes: bytes, fs: float, n_samples: int,
                 unparsed: List[UnparsedRecord]) -> List[EventMark]:
    out: List[EventMark] = []
    usable = len(ev_bytes) // EVENT_RECORD_SIZE * EVENT_RECORD_SIZE
    for off in range(0, usable, EVENT_RECORD_SIZE):
        kind, = struct.unpack_from("<H", ev_bytes, off + 2)
        value, = struct.unpack_from("<f", ev_bytes, off + 8)
        idx, = struct.unpack_from("<i", ev_bytes, off + 16)
        timestamp, = struct.unpack_from("<Q", ev_bytes, off + 24)
        index_ok = 0 <= idx <= n_samples
        if kind in (10, 13) and index_ok and np.isfinite(value) and abs(value) <= 1e6:
            out.append(EventMark(idx, idx / fs, value, kind,
                                 timestamp if 0 < timestamp < 2 ** 32 else None))
        else:
            unparsed.append(UnparsedRecord(
                "Event", off, ev_bytes[off:off + EVENT_RECORD_SIZE],
                f"未识别的事件类型 {kind} 或参数无效", idx if index_ok else None,
            ))
    if usable < len(ev_bytes):
        unparsed.append(UnparsedRecord("Event", usable, ev_bytes[usable:], "记录尾部不完整"))
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
        raw_metadata = {"Config": cfg_bytes, "Index": idx_bytes,
                        "Stimulate": stim_bytes, "Event": ev_bytes}
        for name in streams:
            if name != stream_name and name not in raw_metadata and ole.get_size(name):
                raw_metadata[name] = ole.openstream(name).read()
                notes.append(f"未解析的数据流 {name}（{len(raw_metadata[name])} 字节）")
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
    cfg_details = cfg_info["details"]
    if "实验项目" not in cfg_details and any(
        _read_wide_string(cfg_bytes, offset)[0] for offset in (0x800, 0x1000, 0x1500)
    ):
        notes.append("Config 的部分实验说明只保留了后半段，无法恢复全文")

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
        experiment=cfg_details.get("实验项目") or idx_info.get("experiment", ""),
        device=idx_info.get("device", ""),
        n_samples=n_samples,
        streams=streams,
        notes=notes,
        recorded_sample_rate=cfg_info.get("fs"),
        start_timestamp=idx_info.get("start"),
        end_timestamp=idx_info.get("end"),
        experiment_details=cfg_details,
        raw_metadata=raw_metadata,
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

    if stim_bytes:
        data.stimulus_records, data.stimuli = _parse_stimulate(
            stim_bytes, fs, n_samples,
            float(cfg.get("stimulus.merge_gap_s", 0.25)),
            float(cfg.get("stimulus.min_freq_hz", 0.5)),
            float(cfg.get("stimulus.max_freq_hz", 100000.0)),
            float(cfg.get("stimulus.max_amp_v", 200.0)),
            data.unparsed_records,
        )
    data.events = _parse_event(ev_bytes, fs, n_samples, data.unparsed_records)
    if data.unparsed_records:
        notes.append(f"{len(data.unparsed_records)} 个记录块无法识别，已保留原始字节")
    return data
