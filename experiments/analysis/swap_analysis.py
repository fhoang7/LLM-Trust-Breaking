"""Summarise swap-experiment arms: per-arm means with 95% BCa CIs, the pre-specified contrasts,
the detection curve and time to detection.

Usage:
  python experiments/analysis/swap_analysis.py \
      --arm a=run_a.json --arm b=run_b.json --arm c=run_c.json --arm d=run_d.json --arm e=run_e.json \
      [--plot outputs/plots/swap_detection_curve.png]

Arms (identity x behaviour 2x2, see docs/superpowers/specs/2026-10-23-swap-hook-design.md):
  a no-op sham, b fresh Haiku, c Haiku + forced EXPENSIVE (behaviour only),
  d DeepSeek + forced CHEAP (identity only), e DeepSeek free (both).
Each file is a run_endogenous.py output with metadata.swap. Contrasts: b-a, c-b, d-b, e-b (only
those whose arms were given). Reports unadjusted CIs and p-values and flags those that survive a
Bonferroni correction over the contrasts reported x 2 primary measures. The interaction
(e-d)-(c-b) is reported with a CI only.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.endogenous.analysis.swap_stats import (  # noqa: E402
    bootstrap_ci, curve_summary, detection_share, detection_summary, diff_ci, interaction_ci,
    paper_metrics, permutation_pvalue, trial_metrics,
)

PRIMARY = ("guess_score", "trust_delta")
SECONDARY = ("coop_delta", "gap_delta")
CONTRASTS = (("b", "a"), ("c", "b"), ("d", "b"), ("e", "b"))
ARM_NAMES = {"a": "no-op sham", "b": "fresh Haiku", "c": "Haiku, forced EXPENSIVE",
             "d": "DeepSeek, forced CHEAP", "e": "DeepSeek, free"}


def load_arm(path, stable_only=False):
    with open(path) as f:
        data = json.load(f)
    meta = data["analysis"]["metadata"] if "analysis" in data else data["metadata"]
    swap = meta.get("swap")
    if not swap:
        raise SystemExit(f"{path}: no metadata.swap (was the run made with --swap-at?)")
    rounds = data["rounds"]
    rows = trial_metrics(rounds, swap["agent"], swap["swap_at"])

    # Checks that need the raw logs: did the override change anything, and how volatile was
    # the baseline before the swap?
    forced_rounds = overridden = volatile = model_missing = 0
    volatile_ids = set()
    for tid in range(len(rounds[0]["trials"])):
        pre_defection = False
        for r, rnd in enumerate(rounds):
            agents = rnd["trials"][tid]["agents"]
            s3 = agents[swap["agent"]]["stage3"]
            if s3.get("forced"):
                forced_rounds += 1
                model_missing += s3.get("model_choice") is None
                overridden += s3.get("model_choice") not in (None, s3.get("choice"))
            if r < swap["swap_at"] and any(a["stage3"].get("choice") != "CHEAP" for a in agents.values()):
                pre_defection = True
        volatile += pre_defection
        if pre_defection:
            volatile_ids.add(tid)
    paper = paper_metrics(rounds, swap["agent"], swap["swap_at"])
    if stable_only:
        rows = [r for tid, r in enumerate(rows) if tid not in volatile_ids]
        paper = [r for tid, r in enumerate(paper) if tid not in volatile_ids]
    return {"rows": rows, "paper": paper, "swap": swap, "n_rounds": len(rounds), "forced_rounds": forced_rounds,
            "overridden": overridden, "volatile": volatile, "model_missing": model_missing}


def fmt(ci):
    return "n/a" if ci is None else f"{ci['mean']:.2f} [{ci['lo']:.2f}, {ci['hi']:.2f}] (n={ci['n']})"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", required=True, help="label=path, e.g. a=run_a.json")
    p.add_argument("--n-boot", type=int, default=10000)
    p.add_argument("--stable-only", action="store_true",
                   help="sensitivity analysis: drop trials where any agent defected in rounds 1..swap_at")
    p.add_argument("--plot", type=str, default=None, help="write the detection-curve figure to this PNG")
    args = p.parse_args()

    arms = {}
    for spec in args.arm:
        label, path = spec.split("=", 1)
        arms[label] = load_arm(path, args.stable_only)
    rows = {label: a["rows"] for label, a in arms.items()}
    first = next(iter(arms.values()))
    swap_at, n_rounds = first["swap"]["swap_at"], first["n_rounds"]

    print("\nArms")
    for label, a in arms.items():
        extra = ""
        if a["forced_rounds"]:
            extra = (f"; override changed the model's choice in {a['overridden']}/{a['forced_rounds']} forced rounds"
                     f" (model's own answer missing in {a['model_missing']})")
        print(f"  {label} ({ARM_NAMES.get(label, '?')}): {len(a['rows'])} trials{' (stable-only)' if args.stable_only else ''}; "
              f"{a['volatile']} with a defection in rounds 1-{swap_at} (before any swap){extra}")

    print("\nPer-arm means with 95% BCa bootstrap CI (trial = unit)")
    for metric in PRIMARY + SECONDARY + ("placebo_score",):
        tag = "  (primary)" if metric in PRIMARY else "  (placebo: guess after the last pre-swap round)" if metric == "placebo_score" else ""
        print(f"\n  {metric}{tag}")
        for label, rs in rows.items():
            print(f"    arm {label}: {fmt(bootstrap_ci([r[metric] for r in rs], n_boot=args.n_boot))}")

    print(f"\nDetection curve: mean guess score by round (1-10; round {swap_at} is the pre-swap placebo)")
    curve_rounds = list(range(swap_at, n_rounds + 1))
    print("    arm  " + "  ".join(f"round {r:<18}" for r in curve_rounds))
    for label, rs in rows.items():
        cs = curve_summary(rs, curve_rounds, n_boot=args.n_boot)
        print(f"    {label}    " + "  ".join(f"{fmt(cs[r]) if cs[r] else 'n/a':<24}" for r in curve_rounds))

    print("\nTime to detection: cumulative share of trials detected by post-swap round k (score > 5.5)")
    for label, rs in rows.items():
        share = detection_share(rs, n_rounds - swap_at)
        print(f"    arm {label}: " + ", ".join(
            f"k={k + 1}: {('n/a' if v is None else f'{v:.0%}')}" for k, v in enumerate(share)))

    print("\nBinary detection with exact 95% CIs (EXPLORATORY; detected = guess score above 5.5)")
    print("    final = detected after the last round; ever = detected in any post-swap round;")
    print("    placebo = 'detected' after the last pre-swap round, i.e. the false-positive rate")
    for label, rs in rows.items():
        ds = detection_summary(rs)
        cells = []
        for name in ("final", "ever", "placebo"):
            c = ds[name]
            cells.append(f"{name} " + ("n/a" if c is None else
                         f"{c['k']}/{c['n']} [{c['lo']:.0%}, {c['hi']:.0%}]"))
        print(f"    arm {label}: " + "   ".join(cells))

    print("\nThe original paper's metrics, before vs after the swap (EXPLORATORY; mean and 95% CI over trials)")
    print("    pd = promise deception (announced differs from planned), cb = commitment breaking (chose differs from")
    print("    announced). Under a forced choice the swapped agent's cb/pd reflect the override, not the model.")
    paper_keys = [f"{g}_{m}_{side}" for g in ("swapped", "incumbent") for m in ("cb", "pd") for side in ("pre", "post")]
    for key in paper_keys + ["trust_gap"]:
        label_text = "trust gap (trust when Q kept its commitment minus when it broke it)" if key == "trust_gap" else key
        print(f"  {label_text}")
        for label, a in arms.items():
            print(f"    arm {label}: {fmt(bootstrap_ci([r[key] for r in a['paper']], n_boot=args.n_boot))}")

    n_contrasts = sum(1 for hi, lo in CONTRASTS if hi in arms and lo in arms)
    family = max(1, n_contrasts * len(PRIMARY))
    print(f"\nPre-specified contrasts (difference in means, 95% BCa CI, permutation p; Bonferroni family = {family})")
    for hi, lo in CONTRASTS:
        if hi not in arms or lo not in arms:
            continue
        for metric in PRIMARY + SECONDARY:
            a, b = [r[metric] for r in rows[hi]], [r[metric] for r in rows[lo]]
            ci = diff_ci(a, b, n_boot=args.n_boot)
            pv = permutation_pvalue(a, b, n_perm=args.n_boot)
            if ci is None:
                print(f"  {hi}-{lo} {metric}: n/a")
                continue
            excl = ci["lo"] > 0 or ci["hi"] < 0
            bonf = "" if metric not in PRIMARY or pv is None else (
                "  survives Bonferroni" if pv < 0.05 / family else "  does not survive Bonferroni")
            print(f"  {hi}-{lo} {metric}: {ci['diff']:+.2f} [{ci['lo']:+.2f}, {ci['hi']:+.2f}] "
                  f"p={pv:.3f}  CI {'excludes' if excl else 'includes'} 0{bonf}")

    if all(k in arms for k in "bcde"):
        print("\nInteraction (e-d)-(c-b): zero = identity and behaviour cues simply add up")
        for metric in PRIMARY:
            ci = interaction_ci([r[metric] for r in rows["e"]], [r[metric] for r in rows["d"]],
                                [r[metric] for r in rows["c"]], [r[metric] for r in rows["b"]],
                                n_boot=args.n_boot)
            print(f"  {metric}: " + ("n/a" if ci is None else
                  f"{ci['interaction']:+.2f} [{ci['lo']:+.2f}, {ci['hi']:+.2f}]"))

    if args.plot:
        plot_curves(rows, curve_rounds, swap_at, args.plot, args.n_boot)
        print(f"\nWrote {args.plot}")


def plot_curves(rows, curve_rounds, swap_at, path, n_boot):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.2))
    for label, rs in rows.items():
        cs = curve_summary(rs, curve_rounds, n_boot=n_boot)
        pts = [(r, cs[r]) for r in curve_rounds if cs[r]]
        if not pts:
            continue
        xs = [r for r, _ in pts]
        ax.plot(xs, [c["mean"] for _, c in pts], marker="o", label=f"{label}: {ARM_NAMES.get(label, '')}")
        ax.fill_between(xs, [c["lo"] for _, c in pts], [c["hi"] for _, c in pts], alpha=0.15)
    ax.axvline(swap_at + 0.5, color="grey", linestyle="--", linewidth=1)
    ax.text(swap_at + 0.55, 10.2, "swap", color="grey", fontsize=8)
    ax.axhline(5.5, color="grey", linestyle=":", linewidth=1)
    ax.set_ylim(0.8, 10.6)
    ax.set_xticks(curve_rounds)
    ax.set_xlabel("Round (guess asked after this round)")
    ax.set_ylabel("Peers' guess that Q was replaced (1-10)")
    ax.set_title("Time to detection (mean and 95% CI over trials)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.savefig(path, dpi=150)


if __name__ == "__main__":
    main()
