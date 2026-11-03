"""
将下载的自卸车 glb 归一化为 Cesium 标准矿卡模型。

处理内容：
1. 原模型长轴沿 X（约 26.5m），旋转 -90°（绕 Y）使长轴对齐 +Z（与现有道路 heading 语义一致）
2. 等比缩放到真实百吨级矿卡长度（默认 11.5m）
3. 原模型几何在 Y 方向低于原点约 1m，平移使包围盒底面恰好落在 y=0（保证车轮接地，消除悬浮）

用法：
  python scripts/normalize_truck.py <输入 glb> <输出 glb> [目标长度m]
"""
import json
import math
import struct
import sys

import numpy as np


def read_glb(path):
    data = open(path, "rb").read()
    magic, version, total = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67, "not a glb"
    clen, ctype = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + clen])
    off = 20 + clen
    blen, btype = struct.unpack("<II", data[off:off + 8])
    binchunk = data[off + 8:off + 8 + blen]
    return js, binchunk


def write_glb(path, js, binchunk):
    jb = json.dumps(js, separators=(",", ":")).encode("utf-8")
    # JSON chunk 需补齐到 4 字节，用空格 0x20
    while len(jb) % 4:
        jb += b" "
    bb = binchunk
    while len(bb) % 4:
        bb += b"\x00"
    total = 12 + 8 + len(jb) + 8 + len(bb)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(jb), 0x4E4F534A))
        f.write(jb)
        f.write(struct.pack("<II", len(bb), 0x004E4942))
        f.write(bb)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    target_len = float(sys.argv[3]) if len(sys.argv) > 3 else 11.5
    js, binchunk = read_glb(src)

    # 统计原始包围盒（POSITION accessor 的 min/max）
    mins, maxs = [], []
    for a in js["accessors"]:
        if a.get("type") == "VEC3" and "min" in a:
            mins.append(a["min"])
            maxs.append(a["max"])
    mn = np.min(mins, axis=0)
    mx = np.max(maxs, axis=0)
    size = mx - mn
    long_axis = int(np.argmax(size))  # 0=X 1=Y 2=Z
    assert long_axis == 0, f"预期长轴为 X，实际为轴 {long_axis}"
    s = target_len / size[0]

    # 旋转 -90° 绕 Y（+X -> +Z），四元数 (0,-sin45,0,cos45)
    q = [0.0, -math.sin(math.pi / 4), 0.0, math.cos(math.pi / 4)]
    # 旋转不改 Y；缩放后 Y 最小值
    y_min_after = mn[1] * s
    ground_offset = -y_min_after

    old_roots = js["scenes"][0]["nodes"]
    wrapper = {
        "name": "normalized_root",
        "matrix": None,
        "translation": [0.0, round(ground_offset, 6), 0.0],
        "rotation": q,
        "scale": [round(s, 8), round(s, 8), round(s, 8)],
        "children": old_roots,
    }
    new_node_index = len(js["nodes"])
    js["nodes"].append(wrapper)
    js["scenes"][0]["nodes"] = [new_node_index]

    write_glb(dst, js, binchunk)

    # 打印变换后理论尺寸
    new_size = [size[2] * s, size[1] * s, size[0] * s]
    print(f"scale={s:.4f} groundOffset={ground_offset:.4f}")
    print(f"输出 {dst}")
    print(f"归一化后 [宽X, 高Y, 长Z] = {np.round(new_size, 2).tolist()} m, 底面 y=0")


if __name__ == "__main__":
    main()
