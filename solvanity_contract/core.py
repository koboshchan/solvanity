"""Seed-derived Solana account addresses. No private keys are accepted."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from solders.pubkey import Pubkey

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
OWNERS = {
    "token": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "token2022": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}

def pubkey(value: str | Pubkey) -> Pubkey:
    return value if isinstance(value, Pubkey) else Pubkey.from_string(OWNERS.get(value, value))

def validate_owner(owner: Pubkey) -> None:
    if bytes(owner).endswith(b"ProgramDerivedAddress"):
        raise ValueError("owner ends with forbidden ProgramDerivedAddress marker")

def validate_seed(seed: str) -> bytes:
    raw = seed.encode("utf-8")
    if len(raw) > 32:
        raise ValueError("seed must be at most 32 UTF-8 bytes")
    return raw

def derive(base: str | Pubkey, seed: str, owner: str | Pubkey = "token") -> str:
    base, owner = pubkey(base), pubkey(owner)
    validate_owner(owner)
    raw = validate_seed(seed)
    digest = hashlib.sha256(bytes(base) + raw + bytes(owner)).digest()
    expected = Pubkey.create_with_seed(base, seed, owner)
    if digest != bytes(expected):
        raise RuntimeError("hashlib and solders disagree")
    return str(expected)

def _digits(value: int, width: int) -> list[int]:
    out = [0] * width
    for i in range(width - 1, -1, -1):
        value, out[i] = divmod(value, 58)
    return out

@dataclass(frozen=True)
class Pattern:
    prefix: str = ""
    suffix: str = ""
    ignore_case: bool = False

    def __post_init__(self):
        if len(self.prefix) > 44 or len(self.suffix) > 44:
            raise ValueError("patterns cannot exceed 44 characters")
        for c in self.prefix + self.suffix:
            if not self.variants(c):
                raise ValueError(f"not a base58 character (even under selected case mode): {c!r}")
        if not self.possible():
            raise ValueError("prefix/suffix cannot match a canonical 32-byte base58 address")

    def variants(self, char: str) -> set[int]:
        return {i for i, c in enumerate(ALPHABET)
                if (c.lower() == char.lower() if self.ignore_case else c == char)}

    def matches(self, address: str) -> bool:
        if self.ignore_case:
            address = address.lower()
            return address.startswith(self.prefix.lower()) and address.endswith(self.suffix.lower())
        return address.startswith(self.prefix) and address.endswith(self.suffix)

    def possible(self) -> bool:
        # All-zero pubkey is encoded as exactly 32 leading ones.
        if self.matches("1" * 32):
            return True
        # z leading zero bytes, then n canonical base58 numeric digits.
        for z in range(32):
            for n in range(1, 45 - z):
                length = z + n
                if length < max(32, len(self.prefix), len(self.suffix)):
                    continue
                lo = max(256 ** (31 - z), 58 ** (n - 1))
                hi = min(256 ** (32 - z) - 1, 58 ** n - 1)
                if lo > hi:
                    continue
                allowed = [set(range(58)) for _ in range(length)]
                for i in range(z):
                    allowed[i] = {0}
                allowed[z].discard(0)
                for offset, text in [(0, self.prefix), (length - len(self.suffix), self.suffix)]:
                    for i, c in enumerate(text):
                        allowed[offset + i] &= self.variants(c)
                if any(not a for a in allowed):
                    continue
                low, high = _digits(lo, n), _digits(hi, n)
                @lru_cache(None)
                def feasible(i: int, tight_lo: bool, tight_hi: bool) -> bool:
                    if i == n:
                        return True
                    left = low[i] if tight_lo else 0
                    right = high[i] if tight_hi else 57
                    return any(feasible(i + 1, tight_lo and d == low[i], tight_hi and d == high[i])
                               for d in allowed[z + i] if left <= d <= right)
                if feasible(0, True, True):
                    return True
        return False

def seed_for(namespace: str, counter: int) -> str:
    if len(namespace.encode("utf-8")) > 16:
        raise ValueError("namespace must be at most 16 UTF-8 bytes (16 counter bytes follow)")
    if not 0 <= counter < 2**64:
        raise ValueError("counter must fit uint64")
    return namespace + f"{counter:016x}"

def verify_hit(base, owner, namespace, counter, pattern, claimed_address=None) -> dict:
    seed = seed_for(namespace, counter)
    address = derive(base, seed, owner)
    if claimed_address is not None and address != claimed_address:
        raise RuntimeError("device address failed CPU verification")
    if not pattern.matches(address):
        raise RuntimeError("device match failed CPU verification")
    return {"type": "hit", "base": str(pubkey(base)), "owner": str(pubkey(owner)),
            "seed": seed, "counter": counter, "address": address, "verified": True}
