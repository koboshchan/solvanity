"""Exact base58 pattern counts for uniformly distributed fixed-width bytes.

The count is exact for uniform byte strings, not a proof of the distribution
of compressed Ed25519 public keys. Expected times for wallets are estimates.
Canonical leading zero bytes, valid case alternatives, digit-length bias and
prefix/suffix overlap are all accounted for without enumerating case variants.
"""
from functools import lru_cache
from math import log1p, log

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _below(bound, allowed):
    """Count allowed base58 digit vectors <= bound."""
    if bound < 0:
        return 0
    digits = [0] * len(allowed)
    for i in range(len(digits) - 1, -1, -1):
        bound, digits[i] = divmod(bound, 58)
    tails = [1] * (len(allowed) + 1)
    for i in range(len(allowed) - 1, -1, -1):
        tails[i] = tails[i + 1] * len(allowed[i])
    if bound:
        return tails[0]
    count = 0
    for i, options in enumerate(allowed):
        count += sum(d < digits[i] for d in options) * tails[i + 1]
        if digits[i] not in options:
            return count
    return count + 1


@lru_cache(maxsize=128)
def matching_count(prefix="", suffix="", ignore_case=False, *, byte_length=32):
    """Number of matching byte strings. Invalid/empty intersections return 0."""
    if not isinstance(byte_length, int) or not 1 <= byte_length <= 32:
        raise ValueError("byte_length must be in 1..32")
    if not isinstance(prefix, str) or not isinstance(suffix, str):
        raise ValueError("patterns must be strings")
    # Case folding is deliberately ASCII and counts only actual alphabet symbols.
    if any(not any(a == c or (ignore_case and a.lower() == c.lower())
                   for a in ALPHABET) for c in prefix + suffix):
        return 0
    if ignore_case:
        prefix, suffix = prefix.lower(), suffix.lower()
    max_digits = len(_encode(bytes([255]) * byte_length))
    if max(len(prefix), len(suffix)) > max_digits:
        return 0

    def accepts(ch, position, length):
        if ignore_case:
            ch = ch.lower()
        return ((position >= len(prefix) or ch == prefix[position]) and
                (position < length - len(suffix) or
                 ch == suffix[position - length + len(suffix)]))

    count = 0
    powers = [58 ** i for i in range(max_digits + 1)]
    for zeros in range(byte_length):
        byte_low = 1 << (8 * (byte_length - zeros - 1))
        byte_high = (1 << (8 * (byte_length - zeros))) - 1
        for digits in range(1, max_digits - zeros + 1):
            length = zeros + digits
            if length < max(len(prefix), len(suffix)):
                continue
            low = max(byte_low, powers[digits - 1])
            high = min(byte_high, powers[digits] - 1)
            if low > high or any(not accepts("1", i, length) for i in range(zeros)):
                continue
            allowed = [tuple(d for d, ch in enumerate(ALPHABET)
                             if (i or d) and accepts(ch, zeros + i, length))
                       for i in range(digits)]
            if all(allowed):
                count += _below(high, allowed) - _below(low - 1, allowed)
    zero = "1" * byte_length
    if len(zero) >= max(len(prefix), len(suffix)) and all(
            accepts(ch, i, len(zero)) for i, ch in enumerate(zero)):
        count += 1
    return count


def _encode(data):
    zeros = len(data) - len(data.lstrip(b"\0"))
    n = int.from_bytes(data, "big")
    result = ""
    while n:
        n, d = divmod(n, 58)
        result = ALPHABET[d] + result
    return "1" * zeros + result


def probability(prefix="", suffix="", ignore_case=False):
    return matching_count(prefix, suffix, ignore_case) / (1 << 256)


def estimate(prefix="", suffix="", ignore_case=False, rate=None):
    p = probability(prefix, suffix, ignore_case)
    measured = rate is not None and rate > 0
    mean = 1 / p if p else None
    median = (-log(2) / log1p(-p) if 0 < p < 1 else 1 if p == 1 else None)
    return dict(probability=p, matching_byte_strings=matching_count(prefix, suffix, ignore_case),
                mean_attempts=mean, median_attempts=median,
                mean_seconds=mean / rate if mean is not None and measured else None,
                median_seconds=median / rate if median is not None and measured else None,
                exact_uniform_bytes=True, wallet_distribution_approximate=True)
