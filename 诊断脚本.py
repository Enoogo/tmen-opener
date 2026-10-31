import olefile
import numpy as np

FILE_PATH = r"D:\Files(D)\大二考试\生理学实验\第一次实验\泰盟BL原始数据\1001 - 副本.tmen"
ole = olefile.OleFileIO(FILE_PATH)

# ---- 1. 所有流 ----
print("=== 流列表 ===")
for entry in ole.listdir():
    name = "/".join(entry)
    print(f"  {name:20s} 大小={ole.get_size(entry)}")

# ---- 2. Channel_Data1 前 128 字节 hex ----
ch = ole.openstream("Channel_Data1").read()
print(f"\n=== Channel_Data1 前 128 字节 (总长 {len(ch)} 字节) ===")
for i in range(0, 128, 16):
    chunk = ch[i:i+16]
    hexs = " ".join(f"{b:02x}" for b in chunk)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{i:04x}: {hexs:<48} {asc}")

# ---- 3. 按 int16 解析 ----
arr = np.frombuffer(ch, dtype=np.int16)
print(f"\n=== Channel_Data1 按 int16 解析 ===")
print(f"点数: {len(arr)}")
print(f"min/max/mean/std: {arr.min()} / {arr.max()} / {arr.mean():.2f} / {arr.std():.2f}")
print(f"饱和点数 (>=32700 或 <=-32700): {int(np.sum((arr>=32700)|(arr<=-32700)))}")
print(f"分位数 5/25/50/75/95: {np.percentile(arr,[5,25,50,75,95]).round(2).tolist()}")
print(f"前 60 点: {arr[:60].tolist()}")
print(f"中段 60 点: {arr[len(arr)//2:len(arr)//2+60].tolist()}")
print(f"后 60 点: {arr[-60:].tolist()}")

# ---- 4. Config 流 hex（可能藏着采样率、通道数、缩放系数）----
cfg = ole.openstream("Config").read()
print(f"\n=== Config 前 512 字节 (总长 {len(cfg)} 字节) ===")
for i in range(0, min(512, len(cfg)), 16):
    chunk = cfg[i:i+16]
    hexs = " ".join(f"{b:02x}" for b in chunk)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{i:04x}: {hexs:<48} {asc}")

# ---- 5. Index 流 hex（可能是分段索引）----
idx = ole.openstream("Index").read()
print(f"\n=== Index 前 256 字节 (总长 {len(idx)} 字节) ===")
for i in range(0, min(256, len(idx)), 16):
    chunk = idx[i:i+16]
    hexs = " ".join(f"{b:02x}" for b in chunk)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"{i:04x}: {hexs:<48} {asc}")

ole.close()
