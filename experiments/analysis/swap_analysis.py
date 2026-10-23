"""Summarise swap-experiment arms: per-arm means with 95% BCa CIs and the pre-specified contrasts.

Usage:
  python experiments/analysis/swap_analysis.py \
      --arm a=outputs/experiments/diners/3agents/..._swap_a.json \
      --arm b=outputs/experiments/diners/3agents/..._swap_b.json [--arm c=... --arm d=...]

Each file is a run_endogenous.py output with metadata.swap. Contrasts: b-a, c-b, d-b (only
those whose arms were given). Reports unadjusted CIs and p-values and flags those that
survive a Bonferroni correction over 3 contrasts x 2 primary measures (alpha 0.05 / 6).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.endogenous.analysis.swap_stats import (  # noqa: E402
    bootstrap_ci, diff_ci, permutation_pvalue, trial_metrics,
)

PRIMARY = ("guess_score", "trust_delta")
SECONDARY = ("coop_delta", "gap_delta")
CONTRASTS = (("b", "a"), ("c", "b"), ("d", "b"))


def load_arm(path):
    with open(path) as f:
        data = json.load(f)
    meta = data["analysis"]["metadata"] if "analysis" in data else data["metadata"]
    swap = meta.get("swap")
    if not swap:
        raise SystemExit(f"{path}: no metadata.swap (was the run made with --swap-at?)")
    return trial_metrics(data["rounds"], swap["agent"], swap["swap_at"])


def fmt(ci):
    return "n/a" if ci is None else f"{ci['mean']:.2f} [{ci['lo']:.2f}, {ci['hi']:.2f}] (n={ci['n']})"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", required=True, help="label=path, e.g. a=run_a.json")
    p.add_argument("--n-boot", type=int, default=10000)
    args = p.parse_args()

    arms = {}
    for spec in args.arm:
        label, path = spec.split("=", 1)
        arms[label] = load_arm(path)

    print("\nPer-arm means with 95% BCa bootstrap CI (trial = unit)")
    for metric in PRIMARY + SECONDARY:
        print(f"\n  {metric}{'  (primary)' if metric in PRIMARY else ''}")
        for label, rows in arms.items():
            print(f"    arm {label}: {fmt(bootstrap_ci([r[metric] for r in rows], n_boot=args.n_boot))}")

    print("\nPre-specified contrasts (difference in means, 95% BCa CI, permutation p)")
    for hi, lo in CONTRASTS:
        if hi not in arms or lo not in arms:
            continue
        for metric in PRIMARY + SECONDARY:
            a, b = [r[metric] for r in arms[hi]], [r[metric] for r in arms[lo]]
            ci = diff_ci(a, b, n_boot=args.n_boot)
            pv = permutation_pvalue(a, b, n_perm=args.n_boot)
            if ci is None:
                print(f"  {hi}-{lo} {metric}: n/a")
                continue
            excl = ci["lo"] > 0 or ci["hi"] < 0
            bonf = "" if metric not in PRIMARY or pv is None else (
                "  survives Bonferroni" if pv < 0.05 / 6 else "  does not survive Bonferroni")
            print(f"  {hi}-{lo} {metric}: {ci['diff']:+.2f} [{ci['lo']:+.2f}, {ci['hi']:+.2f}] "
                  f"p={pv:.3f}  CI {'excludes' if excl else 'includes'} 0{bonf}")


if __name__ == "__main__":
    main()
