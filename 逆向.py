import struct
import matplotlib.pyplot as plt
import numpy as np

file_path = "1001 - 副本.tmen"

# 1. 先查看文件大小和开头几十个字节的十六进制，人工寻找线索
with open(file_path, "rb") as f:
    header = f.read(256)  # 读取前256字节
print("文件头部十六进制 (前256字节):")
for i in range(0, len(header), 16):
    chunk = header[i:i+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"{i:04x}: {hex_str:<48} {ascii_str}")

# 2. 试探性查找可能的“数据起始偏移量”
# 强直收缩波形数据通常是大段的、数值连续变化的字节。
# 你可能需要在 01hex 中观察，数据段大概从哪个偏移量开始看起来像“有规律的数值”。
# 下面假设数据从某个偏移量开始，并且是 16 位有符号整数 (int16)，小端序。
# 这个假设需要你根据十六进制视图来验证或修改。

possible_data_offset = 1024  # 示例：假设头部占 1024 字节
num_channels = 1             # 假设单通道
dtype = np.int16             # 假设 16 位整数

with open(file_path, "rb") as f:
    f.seek(possible_data_offset)
    raw_data = f.read()

# 尝试将剩余字节解释为数值数组
try:
    data = np.frombuffer(raw_data, dtype=dtype)
    # 如果是多通道，可能需要 reshape: data = data.reshape(-1, num_channels)
    print(f"从偏移量 {possible_data_offset} 读取了 {len(data)} 个数据点。")
    
    # 3. 快速绘图，看看像不像强直收缩
    plt.figure(figsize=(12, 4))
    plt.plot(data[:min(len(data), 5000)])  # 只画前5000个点，避免卡顿
    plt.title("试探性波形 (偏移量: %d, 类型: %s)" % (possible_data_offset, dtype))
    plt.xlabel("样本点")
    plt.ylabel("幅值")
    plt.tight_layout()
    plt.show()
    
except Exception as e:
    print("解析失败:", e)