"""Minimal Windows process memory scanner (read/write) for Moon Sweepers."""
import ctypes
import ctypes.wintypes as wt
import struct
from decimal import Decimal

import numpy as np

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_READWRITE = 0x04

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("PartitionId", wt.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


k32.OpenProcess.restype = wt.HANDLE
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def find_pid(name="MoonSweepers.exe"):
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION |
                                 PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h:
            raise OSError(f"OpenProcess failed ({ctypes.get_last_error()}). Run as Administrator.")

    def regions(self):
        addr, mbi = 0, MBI()
        while k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and mbi.Protect == PAGE_READWRITE:
                yield base, size
            addr = base + size
            if addr >= 0x7FFFFFFFFFFF:
                break

    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)):
            return None
        return buf.raw[:n.value]

    def write(self, addr, data):
        n = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n))
        return bool(ok) and n.value == len(data)

    # ---- plain numeric types -------------------------------------------------
    def scan(self, dtype, lo, hi):
        dt = np.dtype(dtype)
        hits = []
        for base, size in self.regions():
            data = self.read(base, size)
            if not data:
                continue
            arr = np.frombuffer(data[: len(data) // dt.itemsize * dt.itemsize], dtype=dt)
            idx = np.nonzero((arr >= lo) & (arr <= hi))[0]
            hits.extend((base + idx * dt.itemsize).tolist())
        return hits

    def get(self, dtype, addr):
        dt = np.dtype(dtype)
        b = self.read(addr, dt.itemsize)
        return None if b is None or len(b) < dt.itemsize else np.frombuffer(b, dt)[0].item()

    def put(self, dtype, addr, value):
        return self.write(addr, np.array([value], dtype).tobytes())

    # ---- C# System.Decimal (IL2CPP layout: flags, hi, lo, mid) ---------------
    def scan_decimal(self, lo, hi, min_scale=6):
        """Addresses (4-byte aligned) of positive decimals with lo <= value <= hi."""
        hits = []
        for base, size in self.regions():
            data = self.read(base, size)
            if not data or len(data) < 16:
                continue
            u = np.frombuffer(data[: len(data) // 4 * 4], "<u4")
            f, h, l, m = u[:-3], u[1:-2], u[2:-1], u[3:]
            sc = (f >> 16) & 0xFF
            ok = ((f & 0xFF00FFFF) == 0) & (sc <= 28) & (sc >= min_scale)
            idx = np.nonzero(ok)[0]
            if not len(idx):
                continue
            val = ((h[idx].astype(np.float64) * 18446744073709551616.0 +
                    m[idx].astype(np.float64) * 4294967296.0 + l[idx].astype(np.float64))
                   / np.power(10.0, sc[idx].astype(np.float64)))
            sel = idx[(val >= lo) & (val <= hi)]
            hits.extend((base + sel * 4).tolist())
        return hits

    def scan_wallet_snapshots(self):
        """Find HUD wallet snapshots: [double shown][decimal money][decimal money copy].

        Returns list of (double_addr, decimal_value). Independent of the money amount.
        """
        out = []
        for base, size in self.regions():
            data = self.read(base, size)
            if not data or len(data) < 48:
                continue
            u = np.frombuffer(data[: len(data) // 8 * 8], "<u4")  # 8-byte aligned view
            n = len(u) - 10
            if n <= 0:
                continue
            # candidate decimal at u[k+2..k+5], copy at u[k+6..k+9], double at u[k..k+1]; k even
            k = np.arange(0, n, 2)
            f = u[k + 2]
            sc = (f >> 16) & 0xFF
            ok = ((f & 0xFF00FFFF) == 0) & (sc >= 6) & (sc <= 28)
            k = k[ok]
            if not len(k):
                continue
            same = ((u[k + 2] == u[k + 6]) & (u[k + 3] == u[k + 7]) &
                    (u[k + 4] == u[k + 8]) & (u[k + 5] == u[k + 9]))
            k = k[same]
            for kk in k.tolist():
                addr = base + kk * 4
                d = self.get_decimal(addr + 8)
                shown = self.get("<f8", addr)
                if not d or shown is None:
                    continue
                v = float(d[0])
                if 1 <= v < 1e15 and abs(shown - v) <= max(0.25 * v, 1000):
                    out.append((addr, v))
        return out

    def get_decimal(self, addr):
        b = self.read(addr, 16)
        if not b or len(b) < 16:
            return None
        f, h, l, m = struct.unpack("<4I", b)
        sc = (f >> 16) & 0xFF
        if (f & 0x7F00FFFF) or sc > 28:
            return None
        v = Decimal((h << 64) | (m << 32) | l).scaleb(-sc)
        return (-v if f & 0x80000000 else v), sc

    def put_decimal(self, addr, value, scale):
        n = int((Decimal(value) * (Decimal(10) ** scale)).to_integral_value())
        while n >> 96 and scale > 0:  # too big for 96 bits: drop precision
            scale -= 1
            n = int((Decimal(value) * (Decimal(10) ** scale)).to_integral_value())
        if n < 0 or n >> 96:
            return False
        return self.write(addr, struct.pack("<4I", scale << 16, (n >> 64) & 0xFFFFFFFF,
                                            n & 0xFFFFFFFF, (n >> 32) & 0xFFFFFFFF))
