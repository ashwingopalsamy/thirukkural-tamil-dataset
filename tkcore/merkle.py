"""Merkle proofs over the 1,330 kurals, so one published hash pins every kural and a short proof shows that one
kural's text is in it. The tree is RFC 9162's (certificate transparency): leaf hash = SHA-256(0x00 || leaf),
node hash = SHA-256(0x01 || left || right), split at the largest power of two below the size.

Two trees, both in kural order:
  exact    leaf = canonical JSON {"id", "n", "text"}: the NFC text, lines joined by a newline (text_ta)
  letters  leaf = canonical JSON {"id", "n", "key"}: key = tkcore.signature.compare_key(text), so a quote that differs
           only in spacing, punctuation or how a word is joined checks against the same root
Canonical JSON: sorted keys, no spaces, UTF-8.

  python -m tkcore.merkle            data/agents/merkle_proofs.jsonl (the merkle_proofs config)
  python -m tkcore.merkle --check    fail if that file differs from what data/core gives

roots() is the one function the manifest, the card and the tests read the roots from. Nothing here writes Tamil.
"""
import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

from . import DATA_CORE, ROOT
from .signature import compare_key

PROOFS = ROOT / "data" / "agents" / "merkle_proofs.jsonl"
RULE = ("RFC 9162 Merkle tree, SHA-256, kurals in order. exact leaf: canonical JSON {id, n, text} with text = NFC "
        "lines joined by a newline; letters leaf: {id, n, key} with key = compare_key(text). Canonical JSON = sorted "
        "keys, no spaces, UTF-8.")


def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_bytes(kural_id: str, number: int, text: str, letters: bool = False) -> bytes:
    body = {"key": compare_key(text)} if letters else {"text": unicodedata.normalize("NFC", text)}
    return json.dumps({"id": kural_id, "n": number, **body}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def leaf_hash(leaf: bytes) -> bytes:
    return _h(b"\x00" + leaf)


def node_hash(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def _split(n: int) -> int:
    return 1 << ((n - 1).bit_length() - 1)


def tree_root(hashes: list[bytes]) -> bytes:
    if len(hashes) == 1:
        return hashes[0]
    k = _split(len(hashes))
    return node_hash(tree_root(hashes[:k]), tree_root(hashes[k:]))


def inclusion_path(m: int, hashes: list[bytes]) -> list[bytes]:
    """RFC 9162 section 2.1.3.1: the audit path for leaf m."""
    if len(hashes) == 1:
        return []
    k = _split(len(hashes))
    if m < k:
        return inclusion_path(m, hashes[:k]) + [tree_root(hashes[k:])]
    return inclusion_path(m - k, hashes[k:]) + [tree_root(hashes[:k])]


def verify(index: int, size: int, leaf: bytes, path: list[bytes], root: bytes) -> bool:
    """RFC 9162 section 2.1.3.2."""
    if index >= size:
        return False
    fn, sn, r = index, size - 1, leaf_hash(leaf)
    for p in path:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            while fn and not fn & 1:
                fn >>= 1
                sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


def _leaves(kurals: list[dict], letters: bool) -> list[bytes]:
    return [leaf_hash(leaf_bytes(k["id"], k["number"], "\n".join(k["lines_ta"]), letters)) for k in kurals]


def roots(kurals: list[dict]) -> dict:
    """Both roots, hex. kurals: rows with id, number and lines_ta, in kural order (data/core or the kurals config)."""
    ks = sorted(kurals, key=lambda k: k["number"])
    return {"exact": tree_root(_leaves(ks, False)).hex(), "letters": tree_root(_leaves(ks, True)).hex(),
            "size": len(ks)}


def proofs(kurals: list[dict]) -> list[dict]:
    ks = sorted(kurals, key=lambda k: k["number"])
    exact, letters = _leaves(ks, False), _leaves(ks, True)
    return [{"kural_id": k["id"], "kural_number": k["number"], "leaf_index": i, "tree_size": len(ks),
             "exact_path": [h.hex() for h in inclusion_path(i, exact)],
             "letters_path": [h.hex() for h in inclusion_path(i, letters)]} for i, k in enumerate(ks)]


def load_core() -> list[dict]:
    return [json.loads(l) for l in (DATA_CORE / "kurals.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def render() -> str:
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in proofs(load_core()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not PROOFS.exists() or PROOFS.read_text(encoding="utf-8") != text:
            sys.exit(f"stale: {PROOFS.relative_to(ROOT)}; run python -m tkcore.merkle")
        return
    PROOFS.parent.mkdir(parents=True, exist_ok=True)
    PROOFS.write_text(text, encoding="utf-8")
    r = roots(load_core())
    print(f"{PROOFS.relative_to(ROOT)}: {r['size']} proofs; exact root {r['exact']}; letters root {r['letters']}")


if __name__ == "__main__":
    main()
