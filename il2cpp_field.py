"""Locate an IL2CPP field (by name) in the running game: its class, offset and live values.

Works by finding global-metadata.dat as loaded in memory, then the runtime FieldInfo
whose `name` pointer points at the field's name string.
FieldInfo layout (x64): name*, type*, parent*, int32 offset, uint32 token.
Il2CppClass: image* @0, gc_desc @8, name* @0x10, namespace* @0x18.
Il2CppType: data(8), then uint32 bits: attrs(16) | type(8) | ...
"""
import ctypes
import struct

import numpy as np

import memscan as m

FIELD_ATTRIBUTE_STATIC = 0x10
TYPE_NAMES = {0x02: "bool", 0x08: "int32", 0x09: "uint32", 0x0A: "int64", 0x0C: "float",
              0x0D: "double", 0x0E: "string", 0x11: "valuetype", 0x12: "class"}


def metadata_path(p):
    """global-metadata.dat next to the running game's executable (any install location)."""
    import os
    import ctypes.wintypes as wt
    m.k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    buf = ctypes.create_unicode_buffer(1024)
    n = wt.DWORD(len(buf))
    if not m.k32.QueryFullProcessImageNameW(p.h, 0, buf, ctypes.byref(n)):
        raise OSError("Couldn't read the game's install path.")
    game_dir = os.path.dirname(buf.value)
    return os.path.join(game_dir, "MoonSweepers_Data", "il2cpp_data", "Metadata", "global-metadata.dat")


def all_regions(p):
    addr, mbi = 0, m.MBI()
    while m.k32.VirtualQueryEx(p.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        if mbi.State == m.MEM_COMMIT and mbi.Protect in (0x02, 0x04, 0x08, 0x20, 0x40):
            yield base, size, mbi.Type, mbi.Protect
        addr = base + size
        if addr >= 0x7FFFFFFFFFFF:
            break


def find_metadata(p):
    hdr = open(metadata_path(p), "rb").read(64)
    for base, size, typ, prot in all_regions(p):
        b = p.read(base, 64)
        if b == hdr:
            return base
    # fallback: search inside regions
    for base, size, typ, prot in all_regions(p):
        if size < 1 << 20:
            continue
        d = p.read(base, size)
        if d:
            i = d.find(hdr)
            if i >= 0:
                return base + i
    return None


def find_ptr(p, value, regions=None):
    """Find 8-aligned qwords equal to `value` in private RW memory."""
    hits = []
    for base, size in (regions or p.regions()):
        d = p.read(base, size)
        if not d:
            continue
        a = np.frombuffer(d[: len(d) // 8 * 8], "<u8")
        hits += (base + np.nonzero(a == value)[0] * 8).tolist()
    return hits


def cstr(p, addr, n=80):
    b = p.read(addr, n) or b""
    return b.split(b"\0")[0].decode(errors="replace")


def field_info(p, meta_base, name):
    raw = open(metadata_path(p), "rb").read()
    off = raw.find(b"\0" + name.encode() + b"\0") + 1
    name_ptr = meta_base + off
    out = []
    for fi in find_ptr(p, name_ptr):
        b = p.read(fi, 0x20)
        _, typ, parent, offset, token = struct.unpack("<QQQiI", b)
        tb = p.read(typ, 12) if typ else None
        if not tb or not parent:
            continue
        bits = struct.unpack_from("<I", tb, 8)[0]
        attrs, t = bits & 0xFFFF, (bits >> 16) & 0xFF
        cls = cstr(p, struct.unpack("<Q", p.read(parent + 0x10, 8))[0])
        ns = cstr(p, struct.unpack("<Q", p.read(parent + 0x18, 8))[0])
        out.append(dict(fieldinfo=fi, klass=parent, cls=f"{ns}.{cls}".strip("."), offset=offset,
                        static=bool(attrs & FIELD_ATTRIBUTE_STATIC), type=TYPE_NAMES.get(t, hex(t))))
    return out
