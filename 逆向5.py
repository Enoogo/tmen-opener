import olefile
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
rcParams['axes.unicode_minus'] = False

# ============ 参数 ============
FILE_PATH   = r"D:\Files(D)\大二考试\生理学实验\第一次实验\泰盟BL原始数据\不完全强直收缩.tmen"
CHANNEL     = "Channel_Data1"
FS          = 1000.0       # Config 中读到 1000.0，若时长不对再改
BASELINE_SUBTRACT = True   # 减去前 2000 点均值，让收缩幅度更直观
SMOOTH_WIN  = 1            # 1=不平滑；想更干净可改 5、11
MAX_PLOT    = 12000        # 屏幕最多画多少点，自动降采样显示

# ============ 读取 float32 ============
ole = olefile.OleFileIO(FILE_PATH)
raw = ole.openstream(CHANNEL).read()
ole.close()

arr = np.frombuffer(raw, dtype="<f4").astype(np.float64)
n = len(arr)

baseline = arr[:min(2000, n)].mean() if BASELINE_SUBTRACT else 0.0
data = arr - baseline
t = np.arange(n) / FS

if SMOOTH_WIN > 1:
    kernel = np.ones(SMOOTH_WIN) / SMOOTH_WIN
    data = np.convolve(data, kernel, mode="same")

# ============ 控制台输出（可复制） ============
print("=== Channel_Data1 按 float32 解析 ===")
print(f"点数        : {n}")
print(f"时长        : {n/FS:.3f} s  (FS={FS})")
print(f"原始范围    : {arr.min():.6f} ~ {arr.max():.6f}")
print(f"基线(前2000): {baseline:.6f}")
print(f"去基线范围  : {data.min():.6f} ~ {data.max():.6f}")
print(f"峰峰值      : {data.max()-data.min():.6f}")
print(f"前20点      : {np.round(arr[:20], 6).tolist()}")
print(f"中段20点    : {np.round(arr[n//2:n//2+20], 6).tolist()}")
print(f"后20点      : {np.round(arr[-20:], 6).tolist()}")

# ============ 绘图 ============
step = max(1, n // MAX_PLOT)
t_show, y_show = t[::step], data[::step]

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(t_show, y_show, color="red", linewidth=0.8)
ax.set_xlabel("时间 (s)")
ax.set_ylabel("幅值（去基线）" if BASELINE_SUBTRACT else "幅值")
ax.set_title("强直收缩（滚轮缩放X · ←/→平移 · 右键拖拽 · A适应Y · 双击重置）")
ax.grid(True, alpha=0.3)
ax.format_coord = lambda x, y: f"t={x:.4g}s, y={y:.4f}"

home_xlim = ax.get_xlim()
home_ylim = ax.get_ylim()

# ---- 滚轮缩放横轴（以鼠标为中心） ----
def on_scroll(event):
    if event.inaxes != ax or event.xdata is None:
        return
    x0, x1 = ax.get_xlim()
    xd = event.xdata
    scale = 0.85 if event.button == "up" else 1 / 0.85
    new_w = max((x1 - x0) * scale, 1e-4)
    rel = (x1 - xd) / (x1 - x0)
    ax.set_xlim(xd - new_w * (1 - rel), xd + new_w * rel)
    fig.canvas.draw_idle()
fig.canvas.mpl_connect("scroll_event", on_scroll)

# ---- 键盘：←/→ 平移，A 适应当前 Y ----
def on_key(event):
    if event.key in ("left", "right"):
        x0, x1 = ax.get_xlim()
        w = x1 - x0
        step_ = w * 0.25
        if event.key == "left":
            ax.set_xlim(x0 - step_, x1 - step_)
        else:
            ax.set_xlim(x0 + step_, x1 + step_)
        fig.canvas.draw_idle()
    elif event.key in ("a", "A"):
        x0, x1 = ax.get_xlim()
        mask = (t >= x0) & (t <= x1)
        if np.any(mask):
            y0, y1 = data[mask].min(), data[mask].max()
            pad = max((y1 - y0) * 0.08, 1e-6)
            ax.set_ylim(y0 - pad, y1 + pad)
            fig.canvas.draw_idle()
fig.canvas.mpl_connect("key_press_event", on_key)

# ---- 鼠标右键拖拽平移 ----
_drag = {"x": None, "xlim": None}
def on_press(event):
    if event.button == 3 and event.inaxes == ax and event.xdata is not None:
        _drag["x"] = event.xdata
        _drag["xlim"] = ax.get_xlim()
def on_motion(event):
    if _drag["x"] is None or event.inaxes != ax or event.xdata is None:
        return
    dx = _drag["x"] - event.xdata
    x0, x1 = _drag["xlim"]
    ax.set_xlim(x0 + dx, x1 + dx)
    fig.canvas.draw_idle()
def on_release(event):
    if event.button == 3:
        _drag["x"] = None
fig.canvas.mpl_connect("button_press_event", on_press)
fig.canvas.mpl_connect("motion_notify_event", on_motion)
fig.canvas.mpl_connect("button_release_event", on_release)

# ---- 双击重置 ----
def on_dbl(event):
    if event.dblclick and event.button == 1 and event.inaxes == ax:
        ax.set_xlim(home_xlim)
        ax.set_ylim(home_ylim)
        fig.canvas.draw_idle()
fig.canvas.mpl_connect("button_press_event", on_dbl)

plt.tight_layout()
plt.show()
