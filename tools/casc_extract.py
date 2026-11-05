"""Minimal pure-Python CASC reader for D2R local storage.
Extracts data/global/excel/*.txt tables from the game without external tools.

Layout refs: BastienClement's CASC gist + CascLib sources.
"""
import os
import re
import sys
import zlib
import struct
import hashlib

GAME_DIR = sys.argv[1] if len(sys.argv) > 1 else "D:/AnHw/D2R"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "extracted")

WANTED = [
    "itemstatcost.txt", "weapons.txt", "armor.txt", "misc.txt",
    "uniqueitems.txt", "setitems.txt", "magicprefix.txt", "magicsuffix.txt",
    "runes.txt", "automagic.txt", "cubemain.txt",
    "itemstatcost.bin",
]


def read_build_info():
    with open(os.path.join(GAME_DIR, ".build.info"), "r") as f:
        text = f.read()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = lines[0].split("|")
    row = lines[1].split("|")
    d = dict(zip([h.split("!")[0] for h in header], row))
    return d["Build Key"]


def load_indices():
    """EKey[0:9] -> (archive_no, offset, size)"""
    best = {}
    for sub in ("data", "indices"):
        idx_dir = os.path.join(GAME_DIR, "data", sub)
        if not os.path.isdir(idx_dir):
            continue
        for fn in os.listdir(idx_dir):
            m = re.match(r"^([0-9a-fA-F]{2})([0-9a-fA-F]{8})\.idx$", fn)
            if not m:
                continue
            fileno, version = int(m.group(1), 16), int(m.group(2), 16)
            if fileno not in best or version > best[fileno][0]:
                best[fileno] = (version, os.path.join(idx_dir, fn))
    index = {}
    for fileno, (_, path) in sorted(best.items()):
        data = open(path, "rb").read()
        header2_len = struct.unpack_from("<I", data, 0)[0]
        pos = (8 + header2_len + 0x0F) & 0xFFFFFFF0
        data_len = struct.unpack_from("<I", data, pos)[0]
        pos += 8
        n = data_len // 18
        for i in range(n):
            off = pos + i * 18
            key = data[off:off + 9]
            hi = data[off + 9]
            low = struct.unpack_from(">I", data, off + 10)[0]
            size = struct.unpack_from("<I", data, off + 14)[0]
            archive = (hi << 2) | (low >> 30)
            offset = low & 0x3FFFFFFF
            index[key] = (archive, offset, size)
        print(f"  idx {os.path.basename(path)}: {n} 项")
    return index


INDEX = {}
ENCODING = {}


def find_blob(ekey):
    ent = INDEX.get(ekey[:9])
    if not ent:
        return None
    archive, offset, size = ent
    path = os.path.join(GAME_DIR, "data", "data", f"data.{archive:03d}")
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(size)


def blte_decode(block: bytes) -> bytes:
    if block[:4] != b"BLTE":
        raise ValueError("not BLTE: " + block[:4].hex())
    comp_off = struct.unpack_from(">I", block, 4)[0]
    if comp_off == 0:
        frames = [(len(block) - 8, len(block) * 100)]
        body = 8
    else:
        chunk_count = struct.unpack_from(">H", block, 10)[0]
        frames = []
        p = 12
        for _ in range(chunk_count):
            csize = struct.unpack_from(">I", block, p)[0]
            dsize = struct.unpack_from(">I", block, p + 4)[0]
            frames.append((csize, dsize))
            p += 24
        body = comp_off
    out = bytearray()
    for csize, dsize in frames:
        ftype = block[body:body + 1]
        fdata = block[body + 1: body + csize]
        if ftype == b"N":
            out += fdata
        elif ftype == b"Z":
            out += zlib.decompress(fdata)
        elif ftype == b"E":
            raise ValueError("encrypted frame (unexpected for txt tables)")
        elif ftype == b"F":
            out += blte_decode(fdata)
        else:
            raise ValueError(f"frame type {ftype}")
        body += csize
    return bytes(out)


def read_by_ckey(ckey: bytes) -> bytes:
    """CKey -> encoding -> EKey -> blob -> BLTE decode"""
    ekeys = ENCODING.get(ckey)
    if not ekeys:
        raise KeyError("encoding 中无此 CKey: " + ckey.hex())
    for ek in ekeys:
        block = find_blob(ek)
        if block:
            return blte_decode(block[30:])  # 跳过 30 字节块头
    raise KeyError("idx 中无此 EKey: " + ekeys[0].hex())


def parse_encoding(enc: bytes, anchor_ckey: bytes = None):
    """encoding: 线性扫描入口表 [u8 count][u32BE size][16 CKey][count*16 EKey]
    anchor_ckey: 已知的一个 CKey, 用于校准入口表起点"""
    n = len(enc)
    anchor_pos = enc.find(anchor_ckey) if anchor_ckey else -1

    def walk(start):
        """从 start 走到 anchor; 返回 (ok, entries)
        D2R 条目布局: [u8 count][u32BE size][u8 flags][16 CKey][count*16 EKey]
        表分多块, 块尾 count=0 + 填充; CKey 全局单调递增"""
        p = start
        table = {}
        anchor_ok = anchor_pos < 0
        anchor_entry = anchor_pos - 6 if anchor_pos >= 0 else -1
        last = bytes(16)
        guard = 0
        while p + 22 <= n and guard < 700000:
            guard += 1
            if p == anchor_entry:
                anchor_ok = True
            count = enc[p]
            if count == 0:
                # 块尾: 向前扫到下一个合法入口 (count 合法 + size 合理 + ckey 递增)
                p += 1
                while p + 22 <= n:
                    c2 = enc[p]
                    if 1 <= c2 <= 8:
                        size2 = struct.unpack_from(">I", enc, p + 1)[0]
                        ckey2 = bytes(enc[p + 6:p + 22])
                        if size2 < (1 << 31) and ckey2 > last:
                            break
                    p += 1
                continue
            if count > 8:
                return (False, None)
            size = struct.unpack_from(">I", enc, p + 1)[0]
            if size > (1 << 31):
                return (False, None)
            ckey = bytes(enc[p + 6:p + 22])
            if ckey <= last:
                return (False, None)
            keys = []
            q = p + 22
            for _ in range(count):
                keys.append(bytes(enc[q:q + 16]))
                q += 16
            table[ckey] = keys
            last = ckey
            p = q
            if p > anchor_pos > 0 and not anchor_ok:
                return (False, None)
        return (anchor_ok and len(table) > 1000, table)

    for start in range(16, 0x400):
        if enc[start] == 0 or enc[start] > 8:
            continue
        ok, table = walk(start)
        if ok:
            print(f"  encoding: 入口表起点 {hex(start)}, 共 {len(table)} 条")
            return table
    raise ValueError("encoding 入口表解析失败")


def lookup_ckey(ckey: bytes) -> bytes:
    """在 encoding 二进制里直接定位 CKey 条目, 取其第一个 EKey"""
    pos = 0
    while True:
        pos = ENC_RAW.find(ckey, pos)
        if pos < 0:
            raise KeyError("encoding 中无此 CKey: " + ckey.hex())
        count = ENC_RAW[pos - 6]
        size = struct.unpack_from(">I", ENC_RAW, pos - 5)[0]
        if 1 <= count <= 8 and size < (1 << 31):
            return bytes(ENC_RAW[pos + 16:pos + 32])
        pos += 1


def parse_root(root: bytes) -> dict:
    """D2R root: 每行 '路径|哈希|平台|...' -> 路径 -> 哈希"""
    files = {}
    for line in root.split(b"\n"):
        parts = line.decode("utf-8", "replace").strip().split("|")
        if len(parts) >= 2 and len(parts[1]) == 32:
            path = parts[0]
            if path.startswith("data:"):
                path = path[5:]
            try:
                files[path.lower()] = bytes.fromhex(parts[1])
            except ValueError:
                pass
    print("  root 条目数:", len(files))
    return files


def main():
    global INDEX, ENC_RAW
    build_key = bytes.fromhex(read_build_info())
    print("BuildKey:", build_key.hex())
    bc_path = os.path.join(GAME_DIR, "data", "config", build_key.hex()[:2], build_key.hex()[2:4], build_key.hex())
    bc_text = open(bc_path, "r", encoding="ascii", errors="replace").read()
    def cfg_field(name):
        m = re.search(rf"^{name} = ([0-9a-f ]+)$", bc_text, re.M)
        return m.group(1).split()
    root_ckey = bytes.fromhex(cfg_field("root")[0])
    enc_hashes = cfg_field("encoding")
    enc_ekey = bytes.fromhex(enc_hashes[1])

    print("加载 .idx 索引...")
    INDEX = load_indices()
    print("索引总数:", len(INDEX))

    print("读取 encoding 文件...")
    block = find_blob(enc_ekey)
    if not block:
        raise KeyError("idx 中无 encoding EKey")
    ENC_RAW = blte_decode(block[30:])

    print("读取 root 文件...")
    root_ekey = lookup_ckey(root_ckey)
    block = find_blob(root_ekey)
    if not block:
        raise KeyError("idx 中无 root EKey: " + root_ekey.hex())
    root_raw = blte_decode(block[30:])
    print("root 大小:", len(root_raw))
    root_files = parse_root(root_raw)

    if "--list" in sys.argv:
        pat = sys.argv[sys.argv.index("--list") + 1].lower()
        hits = [k for k in sorted(root_files) if pat in k]
        print(f"匹配 {len(hits)} 条:")
        for k in hits:
            print(" ", k)
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    wanted = list(WANTED)
    # 额外路径: python casc_extract.py <game> <out> -- <extra/path1> <extra/path2>
    if "--" in sys.argv:
        wanted += [p.strip("/").lower() for p in sys.argv[sys.argv.index("--") + 1:]]
    ok = 0
    for name in wanted:
        path = name if "/" in name else "data/global/excel/" + name
        h = root_files.get(path)
        if h is None:
            print("root 中无:", path)
            continue
        # 先当 EKey 直接找, 再当 CKey 走 encoding
        block = find_blob(h)
        if not block:
            try:
                ekey = lookup_ckey(h)
            except KeyError:
                print("无法解析:", path)
                continue
            block = find_blob(ekey)
            if not block:
                print("idx 中无 EKey:", path)
                continue
        data = blte_decode(block[30:])
        out_path = os.path.join(OUT_DIR, os.path.basename(path))
        open(out_path, "wb").write(data)
        print(f"提取成功: {path} ({len(data)} 字节)")
        ok += 1
    print(f"完成, 共 {ok}/{len(wanted)} 个文件")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    main()
