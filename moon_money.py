"""Moon Sweepers - live Moon Money adder.

How it works
------------
The game keeps your wallet as a C# `decimal` (one live "source" value plus a
couple of per-frame snapshot copies used by the HUD). This tool:
  1. asks for your current money (as shown in the BUILD menu),
  2. scans the game's memory for decimals near that value,
  3. keeps only the ones that are LIVE (they change as your income comes in),
  4. adds the amount you choose (max $1,000,000 per add) to those values.

Nothing on disk is touched; the game itself saves the new balance normally.
Run from an Administrator window while the game is running and UNPAUSED.
"""
import sys
import time
from decimal import Decimal, InvalidOperation

import memscan

MAX_ADD = Decimal(1_000_000)
WATCH_SECONDS = 15


def ask_money(prompt):
    while True:
        s = input(prompt).strip().replace(",", "").replace("$", "")
        if s.lower() in ("q", "quit", "exit"):
            sys.exit(0)
        try:
            s = s.lower()
            mult = 1
            if s.endswith("k"):
                s, mult = s[:-1], 1_000
            elif s.endswith("m"):
                s, mult = s[:-1], 1_000_000
            return float(s) * mult
        except ValueError:
            print("  Please type a number like 9250.22 or 16.7k (q to quit).")


def watch(p, addrs, seconds):
    """Return the subset of decimal addresses whose value changed during `seconds`."""
    last = {a: p.get_decimal(a) for a in addrs}
    changed = set()
    end = time.time() + seconds
    while time.time() < end and len(changed) < len(addrs):
        time.sleep(0.5)
        for a in addrs:
            d = p.get_decimal(a)
            if d and last[a] and d[0] != last[a][0]:
                changed.add(a)
            last[a] = d
    return changed


def find_wallet(p, money=None):
    """Locate the wallet without depending on an exact typed amount.

    1. Find the HUD snapshot struct by its shape: [double][decimal][same decimal].
    2. Keep the snapshot(s) that are live (money is moving).
    3. Find the source decimal(s) that track the snapshot value.
    """
    print("  Looking for the wallet (about 20 s)...")
    snaps = p.scan_wallet_snapshots()
    if not snaps:
        return []
    live = watch(p, [a + 8 for a, _ in snaps], WATCH_SECONDS)
    snaps = [(a, v) for a, v in snaps if a + 8 in live] or snaps
    if money and len(snaps) > 1:  # optional hint to pick between several
        snaps.sort(key=lambda s: abs(float(p.get_decimal(s[0] + 8)[0]) - money))
        snaps = snaps[:1]
    if len(snaps) != 1:
        print(f"  Found {len(snaps)} possible wallets.")
        return []
    snap = snaps[0][0]
    v = float(p.get_decimal(snap + 8)[0])
    print(f"  HUD wallet found at ${v:,.2f}. Finding the source value...")

    cands = [a for a in p.scan_decimal(v * 0.9, v * 1.25 + 10_000)
             if a not in (snap + 8, snap + 0x18) and (p.get_decimal(a) or (0, 0))[1] >= 6]
    src = []
    for _ in range(4):  # re-check a few times; payouts land in chunks
        now = float(p.get_decimal(snap + 8)[0])
        src = [a for a in cands
               if (d := p.get_decimal(a)) and abs(float(d[0]) - now) <= max(now * 0.02, 50)]
        livesrc = watch(p, src, 6) if src else set()
        if livesrc:
            src = sorted(livesrc)
            break
    return src + [snap + 8, snap + 0x18]


def main():
    pid = memscan.find_pid()
    if not pid:
        print("MoonSweepers.exe is not running. Start the game and load your save first.")
        return
    p = memscan.Proc(pid)
    print(f"Attached to MoonSweepers.exe (pid {pid}).")
    print("Keep the game UNPAUSED with income flowing - the tool spots the wallet by watching it rise.\n")

    money = None
    while True:
        addrs = find_wallet(p, money)
        if 3 <= len(addrs) <= 8:
            break
        print("  Couldn't lock onto the wallet. Make sure money is coming in.")
        money = ask_money("  Type roughly how much money you have (e.g. 391k) to help, or q to quit: ")

    print("\nWallet found:")
    for a in addrs:
        print(f"  0x{a:X}  ${float(p.get_decimal(a)[0]):,.2f}")

    total = Decimal(0)
    while True:
        s = input(f"\nHow much to add? (1 - {MAX_ADD:,}, Enter/q to quit): ").strip().replace(",", "").replace("$", "")
        if s.lower() in ("", "q", "quit", "exit"):
            break
        try:
            amount = Decimal(s)
        except InvalidOperation:
            print("  Not a number.")
            continue
        if not (0 < amount <= MAX_ADD):
            print(f"  Amount must be between 1 and {MAX_ADD:,}.")
            continue

        before = [p.get_decimal(a) for a in addrs]
        if any(d is None for d in before):
            print("  Wallet moved (save reloaded?). Restart the tool.")
            break
        ok = all(p.put_decimal(a, v + amount, sc) for a, (v, sc) in zip(addrs, before))
        time.sleep(2)
        after = [p.get_decimal(a) for a in addrs]
        gained = min(d[0] for d in after if d) - max(v for v, _ in before)
        if ok and gained >= amount * Decimal("0.99"):
            total += amount
            print(f"  Done. Wallet is now ${float(max(d[0] for d in after if d)):,.2f} "
                  f"(added ${total:,.2f} this session).")
        else:
            print("  The game didn't keep the change. Restart the tool to re-scan.")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except OSError as e:
        print(e)
    input("\nPress Enter to close.")
