import olefile
path = r"D:\Files(D)\大二考试\生理学实验\第一次实验\泰盟BL原始数据\1001 - 副本.tmen"
ole = olefile.OleFileIO(path)
print("内部流列表：")
for entry in ole.listdir():
    name = "/".join(entry)
    print(f"  {name:40s} 大小={ole.get_size(entry)}")



# 饱和数最少的那个 offset 就是真正的数据起点。

import numpy as np

with open(path, "rb") as f:
    raw = f.read()

for off in [1024, 1280, 1536, 1792, 2048, 2560, 3072, 4096]:
    d = np.frombuffer(raw[off:off+2000], dtype=np.int16)
    saturated = np.sum((d >= 32700) | (d <= -32700))
    print(f"offset={off:5d}  前1000点饱和数={saturated:3d}  前10点={d[:10]}")
