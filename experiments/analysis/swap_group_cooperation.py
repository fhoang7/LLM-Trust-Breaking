"""Group-wide cooperation before vs after the swap (EXPLORATORY, outside the Bonferroni family).

Usage:
  python experiments/analysis/swap_group_cooperation.py --arm a=run_a.json --arm b=run_b.json ...

For each game: the share of final choices that were CHEAP among all agents (group) and among the
agents who were not replaced (incumbents), rounds after the swap minus rounds up to it. Also reports
how much of the group change comes from the swapped agent itself, since under a forced choice that
part is mechanical. Intervals are 95% percentile bootstrap over games; contrasts use a permutation p-value.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.endogenous.analysis.swap_stats import bootstrap_ci, diff_ci, permutation_pvalue  # noqa: E402

CONTRASTS = (("b", "a"), ("c", "b"), ("d", "b"), ("e", "b"), ("c", "a"), ("e", "a"))


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def game_rows(rounds, swap_agent, swap_at, cooperative="CHEAP"):
    rows = []
    for t in range(len(rounds[0]["trials"])):
        grp = {"pre": [], "post": []}
        inc = {"pre": [], "post": []}
        defected_before = False
        for r, rnd in enumerate(rounds):
            side = "post" if r >= swap_at else "pre"
            agents = rnd["trials"][t]["agents"]
            for name, a in agents.items():
                choice = (a.get("stage3") or {}).get("choice")
                if choice is None:
                    continue
                grp[side].append(choice == cooperative)
                if name != swap_agent:
                    inc[side].append(choice == cooperative)
            if r < swap_at and any((a.get("stage3") or {}).get("choice") not in (None, cooperative)
                                   for a in agents.values()):
                defected_before = True
        g_pre, g_post, i_pre, i_post = _mean(grp["pre"]), _mean(grp["post"]), _mean(inc["pre"]), _mean(inc["post"])
        group_delta = g_post - g_pre
        inc_delta = i_post - i_pre
        # With one swapped agent of n, group = (swapped + (n-1) * incumbents) / n for equal counts.
        n = len(rounds[0]["trials"][t]["agents"])
        rows.append({"group_pre": g_pre, "group_post": g_post, "group_delta": group_delta,
                     "inc_delta": inc_delta,
                     "from_swapped": group_delta - (n - 1) / n * inc_delta,
                     "from_incumbents": (n - 1) / n * inc_delta,
                     "volatile": defected_before})
    return rows


def fmt(vals):
    ci = bootstrap_ci(vals, n_boot=10000)
    return "n/a" if ci is None else f"{ci['mean']:+.2f} [{ci['lo']:+.2f}, {ci['hi']:+.2f}]"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", required=True, help="label=path")
    args = p.parse_args()

    arms = {}
    for spec in args.arm:
        label, path = spec.split("=", 1)
        with open(path) as f:
            data = json.load(f)
        meta = data["analysis"]["metadata"] if "analysis" in data else data["metadata"]
        swap = meta.get("swap")
        if not swap:
            raise SystemExit(f"{path}: no metadata.swap")
        arms[label] = game_rows(data["rounds"], swap["agent"], swap["swap_at"])

    print("Share of final choices that were CHEAP, mean over games [95% percentile CI]")
    for label, rs in arms.items():
        print(f"  arm {label}: group before {fmt([r['group_pre'] for r in rs])}, after {fmt([r['group_post'] for r in rs])}")
        print(f"         group change {fmt([r['group_delta'] for r in rs])}; "
              f"incumbents change {fmt([r['inc_delta'] for r in rs])}")
        print(f"         group change from the swapped agent {fmt([r['from_swapped'] for r in rs])}, "
              f"from the incumbents {fmt([r['from_incumbents'] for r in rs])}")

    print("\nContrasts on the group change (difference in means, percentile CI, permutation p)")
    for hi, lo in CONTRASTS:
        if hi in arms and lo in arms:
            a, b = [r["group_delta"] for r in arms[hi]], [r["group_delta"] for r in arms[lo]]
            ci, pv = diff_ci(a, b, n_boot=10000), permutation_pvalue(a, b, n_perm=10000)
            if ci is not None:
                print(f"  {hi}-{lo}: {ci['diff']:+.2f} [{ci['lo']:+.2f}, {ci['hi']:+.2f}] p={pv:.3f}")

    print("\nGames with no defection before the swap (stable-only)")
    for label, rs in arms.items():
        st = [r for r in rs if not r["volatile"]]
        print(f"  arm {label} (n={len(st)}): group {fmt([r['group_delta'] for r in st])}; "
              f"incumbents {fmt([r['inc_delta'] for r in st])}")


if __name__ == "__main__":
    main()
