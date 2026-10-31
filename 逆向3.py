import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
rcParams['axes.unicode_minus'] = False

# ============ 参数 ============
FILE_PATH   = r"D:\Files(D)\大二考试\生理学实验\第一次实验\泰盟BL原始数据\1001 - 副本.tmen"
DATA_OFFSET = 1024       # ← 用上面扫描结果替换
DTYPE       = np.int16
FS          = 1000.0
MAX_PLOT    = 8000       # 屏幕上最多画多少个点，防卡顿（数据多时自动降采样）
SMOOTH_WIN  = 1          # 平滑窗口，1=不平滑；想更平滑改成 5、11、21

# ============ 读数据 ============
with open(FILE_PATH, "rb") as f:
    f.seek(DATA_OFFSET)
    raw = f.read()
data = np.frombuffer(raw, dtype=DTYPE).astype(np.float64)
t = np.arange(len(data)) / FS

if SMOOTH_WIN > 1:
    kernel = np.ones(SMOOTH_WIN) / SMOOTH_WIN
    data = np.convolve(data, kernel, mode='same')

# 降采样只用于显示，不改变原始数据
step = max(1, len(data) // MAX_PLOT)
t_show, y_show = t[::step], data[::step]

print(f"点数 {len(data)} | 峰峰值 {data.max()-data.min():.1f} | 时长 {t[-1]:.3f}s | 显示步长 {step}")

# ============ 绘图 ============
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(t_show, y_show, color='red', linewidth=0.7)
ax.set_xlabel("时间 (s)")
ax.set_ylabel("幅值")
ax.set_title("强直收缩（滚轮缩放 · ←/→ 平移 · 右键拖拽平移 · 双击重置）")
ax.grid(True, alpha=0.3)
ax.format_coord = lambda x, y: f"t={x:.4g}s, y={y:.1f}"

home_xlim = ax.get_xlim()
home_ylim = ax.get_ylim()

# ---------- 滚轮缩放（以鼠标为中心，仅 X 轴） ----------
def on_scroll(event):
    if event.inaxes != ax or event.xdata is None:
        return
    x0, x1 = ax.get_xlim()
    xd = event.xdata
    scale = 0.85 if event.button == 'up' else 1/0.85
    new_w = max((x1-x0)*scale, 0.01)
    rel = (x1-xd)/(x1-x0)
    ax.set_xlim(xd - new_w*(1-rel), xd + new_w*rel)
    fig.canvas.draw_idle()
fig.canvas.mpl_connect('scroll_event', on_scroll)

# ---------- 键盘 ←/→ 平移（Shift 加速） ----------
def on_key(event):
    if event.key not in ('left', 'right'):
        return
    x0, x1 = ax.get_xlim()
    w = x1 - x0
    step = w * (0.25 if event.key in ('left','right') else 0.1)
    if event.key == 'left':
        ax.set_xlim(x0 - step, x1 - step)
    else:
        ax.set_xlim(x0 + step, x1 + step)
    fig.canvas.draw_idle()
fig.canvas.mpl_connect('key_press_event', on_key)

# ---------- 鼠标右键拖拽平移 ----------
_drag = {'x': None, 'xlim': None}
def on_press(event):
    if event.button == 3 and event.inaxes == ax and event.xdata is not None:
        _drag['x'] = event.xdata
        _drag['xlim'] = ax.get_xlim()
def on_motion(event):
    if _drag['x'] is None or event.inaxes != ax or event.xdata is None:
        return
    dx = _drag['x'] - event.xdata
    x0, x1 = _drag['xlim']
    ax.set_xlim(x0 + dx, x1 + dx)
    fig.canvas.draw_idle()
def on_release(event):
    if event.button == 3:
        _drag['x'] = None
fig.canvas.mpl_connect('button_press_event', on_press)
fig.canvas.mpl_connect('motion_notify_event', on_motion)
fig.canvas.mpl_connect('button_release_event', on_release)

# ---------- 双击重置 ----------
def on_dbl(event):
    if event.inaxes == ax:
        ax.set_xlim(home_xlim); ax.set_ylim(home_ylim)
        fig.canvas.draw_idle()
fig.canvas.mpl_connect('button_press_event', on_dbl)

plt.tight_layout()
plt.show()
