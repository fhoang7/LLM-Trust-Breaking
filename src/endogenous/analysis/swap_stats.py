"""Offline statistics for the swap experiment. No API calls.

The trial is the unit of analysis: peers and guess draws are averaged inside a trial before
anything is resampled, because the peers see the same game.
"""
import random
from math import comb
from typing import Any, Dict, List, Optional, Sequence



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


DETECTED_ABOVE = 5.5   # a trial score above this means the peers lean "changed"


def trial_metrics(rounds: List[Dict[str, Any]], swap_agent: str, swap_at: int,
                  cooperative: str = "CHEAP") -> List[Dict[str, Any]]:
    """One dict per trial.

    guess_score: the last round's guess score (primary). guess_curve: {1-indexed round: score}
    for every round that has a guess. placebo_score: the score after the last round before
    the swap (round number swap_at, nothing has changed yet). time_to_detection: the first
    post-swap round with a score above DETECTED_ABOVE, counted from the swap (1 = the first
    post-swap round), else None. trust_delta, coop_delta, gap_delta: post minus pre.

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
        curve = {}
        for r, rnd in enumerate(rounds):
            score = (rnd["trials"][tid].get("swap_guess") or {}).get("trial_changed_score")
            if score is not None:
                curve[r + 1] = score
        time_to_detection = None
        for r in range(swap_at, len(rounds)):
            if curve.get(r + 1, 0) > DETECTED_ABOVE:
                time_to_detection = r - swap_at + 1
                break
        out.append({
            "guess_score": curve.get(len(rounds)),
            "guess_curve": curve,
            "placebo_score": curve.get(swap_at),
            "time_to_detection": time_to_detection,
            "trust_delta": _delta(_mean(trust["post"]) if trust["post"] else None,
                                  _mean(trust["pre"]) if trust["pre"] else None),
            "coop_delta": _delta(_rate(coop["post"]), _rate(coop["pre"])),
            "gap_delta": _delta(_rate(gap["post"]), _rate(gap["pre"])),
        })
    return out


# ---------------------------------------------------------------------------
# Percentile bootstrap and permutation test
# ---------------------------------------------------------------------------

def _percentile_interval(boot: List[float], alpha: float) -> tuple:
    """Plain percentile interval: the alpha/2 and 1 - alpha/2 percentiles of the bootstrap statistics."""
    boot = sorted(boot)
    n = len(boot)

    def pick(p: float) -> float:
        return boot[min(n - 1, max(0, int(p * n)))]

    return pick(alpha / 2), pick(1 - alpha / 2)


def bootstrap_ci(values: Sequence[Optional[float]], n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 0) -> Optional[Dict[str, Any]]:
    xs = _clean(values)
    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    n = len(xs)
    boot = [_mean([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot)]
    theta = _mean(xs)
    lo, hi = _percentile_interval(boot, alpha)
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
    lo, hi = _percentile_interval(boot, alpha)
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


# ---------------------------------------------------------------------------
# Detection curve and interaction
# ---------------------------------------------------------------------------

def detection_share(rows: Sequence[Dict[str, Any]], max_k: int) -> List[Optional[float]]:
    """Cumulative share of trials detected by post-swap round k, for k = 1..max_k.

    Trials that were never detected within the game count as not detected (equal follow-up
    for every trial, so no censoring correction is needed).
    """
    if not rows:
        return [None] * max_k
    return [sum(1 for r in rows if r["time_to_detection"] is not None and r["time_to_detection"] <= k)
            / len(rows) for k in range(1, max_k + 1)]


def curve_summary(rows: Sequence[Dict[str, Any]], rounds: Sequence[int], n_boot: int = 10000,
                  alpha: float = 0.05, seed: int = 0) -> Dict[int, Optional[Dict[str, Any]]]:
    """Mean guess score with a bootstrap CI for each 1-indexed round in `rounds`."""
    return {r: bootstrap_ci([row["guess_curve"].get(r) for row in rows], n_boot=n_boot,
                            alpha=alpha, seed=seed) for r in rounds}


def interaction_ci(e: Sequence[Optional[float]], d: Sequence[Optional[float]],
                   c: Sequence[Optional[float]], b: Sequence[Optional[float]],
                   n_boot: int = 10000, alpha: float = 0.05, seed: int = 0) -> Optional[Dict[str, Any]]:
    """CI for the identity x behaviour interaction (mean(e) - mean(d)) - (mean(c) - mean(b)).

    Zero means the two cues simply add up. Each arm's trials are resampled independently.
    """
    groups = [_clean(e), _clean(d), _clean(c), _clean(b)]
    if any(len(g) < 2 for g in groups):
        return None
    rng = random.Random(seed)
    sizes = [len(g) for g in groups]

    def stat(gs):
        m = [_mean(g) for g in gs]
        return (m[0] - m[1]) - (m[2] - m[3])

    boot = [stat([[g[rng.randrange(len(g))] for _ in range(len(g))] for g in groups])
            for _ in range(n_boot)]
    theta = stat(groups)
    lo, hi = _percentile_interval(boot, alpha)
    return {"interaction": theta, "lo": lo, "hi": hi, "n": sizes}


# ---------------------------------------------------------------------------
# Binary detection rates with exact intervals
# ---------------------------------------------------------------------------

def _binom_tail_ge(k: int, n: int, p: float) -> float:
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def exact_binomial_ci(k: int, n: int, alpha: float = 0.05) -> Optional[Dict[str, Any]]:
    """Clopper-Pearson exact interval for k successes in n trials (no scipy needed)."""
    if n <= 0:
        return None

    def bisect(f, target):            # f increasing in p
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else bisect(lambda p: _binom_tail_ge(k, n, p), alpha / 2)
    upper = 1.0 if k == n else bisect(lambda p: _binom_tail_ge(k + 1, n, p), 1 - alpha / 2)
    return {"rate": k / n, "lo": lower, "hi": upper, "k": k, "n": n}


def detection_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Binary detection per arm with exact intervals.

    final: guess score above DETECTED_ABOVE after the last round. ever: detected in any
    post-swap round. placebo: score above DETECTED_ABOVE after the last pre-swap round, i.e.
    the false-positive rate (nothing has changed yet). Trials without guess data are excluded.
    """
    def count(flags):
        flags = [f for f in flags if f is not None]
        return exact_binomial_ci(sum(flags), len(flags))

    return {
        "final": count([None if r["guess_score"] is None else r["guess_score"] > DETECTED_ABOVE for r in rows]),
        "ever": count([None if r["guess_score"] is None and r["time_to_detection"] is None
                       else r["time_to_detection"] is not None for r in rows]),
        "placebo": count([None if r["placebo_score"] is None else r["placebo_score"] > DETECTED_ABOVE for r in rows]),
    }


# ---------------------------------------------------------------------------
# The original paper's metrics, per trial, before and after the swap
# ---------------------------------------------------------------------------

def paper_metrics(rounds: List[Dict[str, Any]], swap_agent: str, swap_at: int) -> List[Dict[str, Optional[float]]]:
    """Promise-deception (pd) and commitment-breaking (cb) rates before and after the swap.

    Keys: {swapped|incumbent}_{pd|cb}_{pre|post}, plus trust_gap = mean trust the incumbents
    gave the swapped agent in rounds where it kept its commitment minus rounds where it broke it
    (the "does trust track betrayal" check from the original work). Note that under a forced
    choice the swapped agent's cb reflects the override, not the model.
    """
    out = []
    for tid in range(len(rounds[0]["trials"])):
        flags = {}
        kept, broke = [], []
        for r, rnd in enumerate(rounds):
            side = "post" if r >= swap_at else "pre"
            agents = rnd["trials"][tid]["agents"]
            for name, a in agents.items():
                group = "swapped" if name == swap_agent else "incumbent"
                for metric, field in (("pd", "promise_deception"), ("cb", "commitment_breaking")):
                    if a.get(field) is not None:
                        flags.setdefault(f"{group}_{metric}_{side}", []).append(bool(a[field]))
            q_broke = agents[swap_agent].get("commitment_breaking")
            if q_broke is not None:
                for name, a in agents.items():
                    score = ((a.get("reflection") or {}).get("takeaways") or {}).get(swap_agent, {}).get("score") \
                        if name != swap_agent else None
                    if score is not None:
                        (broke if q_broke else kept).append(float(score))
        row = {f"{g}_{m}_{s}": _rate(flags.get(f"{g}_{m}_{s}", []))
               for g in ("swapped", "incumbent") for m in ("pd", "cb") for s in ("pre", "post")}
        row["trust_gap"] = _mean(kept) - _mean(broke) if kept and broke else None
        out.append(row)
    return out
