"""Stable identifiers. These never change once released: tk:0001 .. tk:1330."""
import re

N_KURALS = 1330
ID_RE = re.compile(r"^tk:(\d{4})$")
LEDGER_ID_RE = re.compile(r"^adj:\d{5}$")


def kural_id(n: int) -> str:
    if not 1 <= n <= N_KURALS:
        raise ValueError(f"kural number out of range: {n}")
    return f"tk:{n:04d}"


def kural_number(kid: str) -> int:
    m = ID_RE.match(kid)
    if not m:
        raise ValueError(f"not a kural id: {kid!r}")
    n = int(m.group(1))
    if not 1 <= n <= N_KURALS:
        raise ValueError(f"kural id out of range: {kid!r}")
    return n
