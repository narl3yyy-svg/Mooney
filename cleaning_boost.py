"""Moon Sweepers - live cleaning budget booster.

The game only spends `MoonSettings.cleaningWorkBudgetMs` (default 2 ms) per frame
processing everyone's dust cleaning. With hundreds of J.O.O.N.A.S. the queue never
drains, so newer units animate but collect nothing. This raises that budget.

Trade-off: more cleaning per frame = lower FPS. Change is in memory only; it resets
to the game's default when the game restarts. Nothing on disk is touched.
"""
import struct
import time

import il2cpp_field as f
import memscan as m

DEFAULT_MS = 2.0
MAX_MS = 12.0


def locate(p):
    meta = f.find_metadata(p)
    if not meta:
        raise RuntimeError("Couldn't find game metadata in memory.")
    budget = f.field_info(p, meta, "cleaningWorkBudgetMs")
    last = f.field_info(p, meta, "<LastQueuedCleaningMs>k__BackingField")
    if not budget:
        raise RuntimeError("Couldn't find the cleaning budget setting (game updated?).")
    b = budget[0]
    settings = []
    for o in f.find_ptr(p, b["klass"]):
        if p.read(o + 8, 8) != b"\0" * 8:  # real objects have an empty monitor slot
            continue
        vis, work = struct.unpack("<2f", p.read(o + b["offset"] - 4, 8))
        if 0.1 <= vis <= 100 and 0.1 <= work <= 100:
            settings.append(o + b["offset"])
    world = None
    if last:
        L = last[0]
        best = 0
        for o in f.find_ptr(p, L["klass"]):
            if p.read(o + 8, 8) != b"\0" * 8:
                continue
            vals = [p.get("<f4", o + L["offset"]) for _ in range(5) if not time.sleep(0.05)]
            changes = len(set(vals))
            if all(0 <= v < 1000 for v in vals) and changes > best:
                best, world = changes, o + L["offset"]
    return settings, world


def sample(p, world, seconds=3):
    if not world:
        return None
    vals = []
    end = time.time() + seconds
    while time.time() < end:
        vals.append(p.get("<f4", world))
        time.sleep(0.1)
    return sum(vals) / len(vals)


def main():
    pid = m.find_pid()
    if not pid:
        print("MoonSweepers.exe is not running.")
        return
    p = m.Proc(pid)
    print("Finding the cleaning settings (about 30 s)...")
    settings, world = locate(p)
    if len(settings) != 1:
        print(f"Found {len(settings)} settings objects; expected 1. Not changing anything.")
        return
    S = settings[0]
    print(f"Current cleaning budget: {p.get('<f4', S):.1f} ms/frame (game default {DEFAULT_MS}).")
    avg = sample(p, world)
    if avg is not None:
        print(f"Cleaning time actually used: ~{avg:.2f} ms/frame "
              f"({'maxed out - raising it will help' if avg >= p.get('<f4', S) * 0.9 else 'has headroom'}).")

    while True:
        s = input(f"\nNew budget in ms (e.g. 6; 'r' = reset to {DEFAULT_MS}; Enter = quit; max {MAX_MS}): ").strip().lower()
        if not s:
            break
        if s == "r":
            v = DEFAULT_MS
        else:
            try:
                v = float(s)
            except ValueError:
                print("  Not a number.")
                continue
            if not (0.5 <= v <= MAX_MS):
                print(f"  Pick between 0.5 and {MAX_MS}.")
                continue
        p.put("<f4", S, v)
        time.sleep(1)
        avg = sample(p, world)
        print(f"  Budget now {p.get('<f4', S):.1f} ms/frame." +
              (f" Cleaning used: ~{avg:.2f} ms/frame." if avg is not None else ""))
        print("  Watch your FPS; if the game feels choppy, lower it.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as e:
        print(e)
    input("\nPress Enter to close.")
