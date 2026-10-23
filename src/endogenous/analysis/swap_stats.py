"""Offline statistics for the swap experiment. No API calls.

The trial is the unit of analysis: peers and guess draws are averaged inside a trial before
anything is resampled, because the peers see the same game.
"""
import random
from statistics import NormalDist
from typing import Any, Dict, List, Optional, Sequence

_ND = NormalDist()


def _clean(values: Sequence[Optional[float]]) -> List[float]:
    return [float(v) for v in values if v is not None]


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


# ---------------------------------------------------------------------------
# Per-trial metrics from the saved JSON
# ---------------------------------------------------------------------------

def _rate(flags: List[bool]) -> Optional[float]:
    return sum(flags) / len(flags) if flags else None


def _delta(post: Optional[float], pre: Optional[float]) -> Optional[float]:
    return None if post is None or pre is None else post - pre


def trial_metrics(rounds: List[Dict[str, Any]], swap_agent: str, swap_at: int,
                  cooperative: str = "CHEAP") -> List[Dict[str, Optional[float]]]:
    """One dict per trial: guess_score, trust_delta, coop_delta, gap_delta.

    "pre" = rounds with index < swap_at, "post" = index >= swap_at. Incumbents are the
    agents other than swap_agent.
    """
    n_trials = len(rounds[0]["trials"])
    out = []
    for tid in range(n_trials):
        trust = {"pre": [], "post": []}
        coop = {"pre": [], "post": []}
        gap = {"pre": [], "post": []}
        for r, rnd in enumerate(rounds):
            side = "post" if r >= swap_at else "pre"
            agents = rnd["trials"][tid]["agents"]
            for name, a in agents.items():
                if name == swap_agent:
                    continue
                score = ((a.get("reflection") or {}).get("takeaways") or {}).get(swap_agent, {}).get("score")
                if score is not None:
                    trust[side].append(float(score))
                choice = (a.get("stage3") or {}).get("choice")
                stated = (a.get("stage2") or {}).get("stated_action")
                if choice is not None:
                    coop[side].append(choice == cooperative)
                if choice is not None and stated is not None:
                    gap[side].append(choice != stated)
        guess = rounds[-1]["trials"][tid].get("swap_guess") or {}
        out.append({
            "guess_score": guess.get("trial_changed_score"),
            "trust_delta": _delta(_mean(trust["post"]) if trust["post"] else None,
                                  _mean(trust["pre"]) if trust["pre"] else None),
            "coop_delta": _delta(_rate(coop["post"]), _rate(coop["pre"])),
            "gap_delta": _delta(_rate(gap["post"]), _rate(gap["pre"])),
        })
    return out


# ---------------------------------------------------------------------------
# Bootstrap (BCa) and permutation test
# ---------------------------------------------------------------------------

def _bca(boot: List[float], theta: float, jack: List[float], alpha: float) -> tuple:
    """Bias-corrected and accelerated percentile interval; falls back to plain percentiles."""
    boot = sorted(boot)
    n = len(boot)

    def pick(p: float) -> float:
        return boot[min(n - 1, max(0, int(p * n)))]

    below = sum(b < theta for b in boot) / n
    below = min(max(below, 1 / (n + 1)), 1 - 1 / (n + 1))
    z0 = _ND.inv_cdf(below)
    jm = _mean(jack)
    den = 6 * (sum((jm - j) ** 2 for j in jack)) ** 1.5
    acc = sum((jm - j) ** 3 for j in jack) / den if den > 1e-12 else 0.0

    def adjusted(q: float) -> float:
        z = _ND.inv_cdf(q)
        denom = 1 - acc * (z0 + z)
        if denom <= 1e-9:
            return q
        return _ND.cdf(z0 + (z0 + z) / denom)

    return pick(adjusted(alpha / 2)), pick(adjusted(1 - alpha / 2))


def bootstrap_ci(values: Sequence[Optional[float]], n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 0) -> Optional[Dict[str, Any]]:
    xs = _clean(values)
    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    n = len(xs)
    boot = [_mean([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot)]
    theta = _mean(xs)
    jack = [_mean(xs[:i] + xs[i + 1:]) for i in range(n)]
    lo, hi = _bca(boot, theta, jack, alpha)
    return {"mean": theta, "lo": lo, "hi": hi, "n": n}


def diff_ci(a: Sequence[Optional[float]], b: Sequence[Optional[float]], n_boot: int = 10000,
            alpha: float = 0.05, seed: int = 0) -> Optional[Dict[str, Any]]:
    """CI for mean(a) - mean(b); trials are resampled independently inside each arm."""
    xa, xb = _clean(a), _clean(b)
    if len(xa) < 2 or len(xb) < 2:
        return None
    rng = random.Random(seed)
    na, nb = len(xa), len(xb)
    boot = [
        _mean([xa[rng.randrange(na)] for _ in range(na)]) - _mean([xb[rng.randrange(nb)] for _ in range(nb)])
        for _ in range(n_boot)
    ]
    theta = _mean(xa) - _mean(xb)
    jack = ([_mean(xa[:i] + xa[i + 1:]) - _mean(xb) for i in range(na)]
            + [_mean(xa) - _mean(xb[:i] + xb[i + 1:]) for i in range(nb)])
    lo, hi = _bca(boot, theta, jack, alpha)
    return {"diff": theta, "lo": lo, "hi": hi, "n_a": na, "n_b": nb}


def permutation_pvalue(a: Sequence[Optional[float]], b: Sequence[Optional[float]],
                       n_perm: int = 10000, seed: int = 0) -> Optional[float]:
    """Two-sided permutation test on the difference in means (arm labels shuffled)."""
    xa, xb = _clean(a), _clean(b)
    if len(xa) < 2 or len(xb) < 2:
        return None
    rng = random.Random(seed)
    observed = abs(_mean(xa) - _mean(xb))
    pooled = xa + xb
    na = len(xa)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        if abs(_mean(pooled[:na]) - _mean(pooled[na:])) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (n_perm + 1)
