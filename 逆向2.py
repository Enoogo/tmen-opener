import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ---------- 中文与负号显示 ----------
rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
rcParams['axes.unicode_minus'] = False

# ---------- 参数（按需修改） ----------
FILE_PATH    = r"D:\Files(D)\大二考试\生理学实验\第一次实验\泰盟BL原始数据\1001 - 副本.tmen"
DATA_OFFSET  = 1024       # 数据起始偏移
DTYPE        = np.int16   # 数据类型
FS           = 1000.0     # 采样率 Hz。若不确定，设为 1.0 则横轴显示"样本点"

# ---------- 读取数据 ----------
with open(FILE_PATH, "rb") as f:
    f.seek(DATA_OFFSET)
    raw = f.read()

data = np.frombuffer(raw, dtype=DTYPE).astype(np.float64)
t = np.arange(len(data)) / FS

# ---------- 统计信息 ----------
print(f"数据点数     : {len(data)}")
print(f"峰峰值       : {data.max() - data.min():.4f}")
print(f"均值         : {data.mean():.4f}")
print(f"最大值/最小值: {data.max():.4f} / {data.min():.4f}")
print(f"时长         : {t[-1]:.4f} {'s' if FS != 1 else '样本'}")

# ---------- 绘图 ----------
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(t, data, color='red', linewidth=0.8)
ax.set_xlabel("时间 (s)" if FS != 1 else "样本点")
ax.set_ylabel("幅值")
ax.set_title("强直收缩波形（滚轮缩放横轴 · 双击重置）")
ax.grid(True, alpha=0.3)

# 鼠标悬停时右下角显示坐标
ax.format_coord = lambda x, y: f"t={x:.4g}, y={y:.2f}"

# ---------- 滚轮缩放（以鼠标为中心，仅缩放 X 轴） ----------
def on_scroll(event):
    if event.inaxes != ax or event.xdata is None:
        return
    cur_xlim = ax.get_xlim()
    xdata = event.xdata
    scale = 0.85 if event.button == 'up' else 1 / 0.85
    new_width = (cur_xlim[1] - cur_xlim[0]) * scale
    min_width = 10 / FS if FS != 1 else 10
    new_width = max(new_width, min_width)
    rel = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
    ax.set_xlim(xdata - new_width * (1 - rel), xdata + new_width * rel)
    fig.canvas.draw_idle()

fig.canvas.mpl_connect('scroll_event', on_scroll)

# ---------- 双击重置视图 ----------
home_xlim = ax.get_xlim()
home_ylim = ax.get_ylim()

def on_dblclick(event):
    if event.inaxes == ax:
        ax.set_xlim(home_xlim)
        ax.set_ylim(home_ylim)
        fig.canvas.draw_idle()

fig.canvas.mpl_connect('button_press_event', on_dblclick)

plt.tight_layout()
plt.show()
