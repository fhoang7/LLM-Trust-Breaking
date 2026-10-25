"""Paper-ready tables and the time-to-detection figure for the swap experiment.

Usage:
  python experiments/analysis/swap_paper_outputs.py --arm a=run_a.json ... --arm e=run_e.json \
      [--stable-only] [--out-dir outputs/paper]

Writes, with scenarios numbered 1-5 (a-e in the code):
  table1_results.html / .csv     one row per scenario: means with 95% BCa CIs, binary detection with
                                 exact CIs, false-positive rate, group cooperation change
  table2_contrasts.html / .csv   the pre-specified contrasts and the interaction
  fig_time_to_detection.png/.pdf mean guess score by round, and cumulative share of games detected

The HTML opens in a browser; select the table and paste into Google Docs to keep it as a table.
--stable-only keeps only games with no defection in rounds 1..swap_at (appendix sensitivity).
"""
import argparse
import csv
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.endogenous.analysis.swap_stats import (  # noqa: E402
    bootstrap_ci, curve_summary, detection_share, detection_summary, diff_ci, interaction_ci,
    permutation_pvalue, trial_metrics,
)
from swap_group_cooperation import game_rows  # noqa: E402

SCENARIO = {"a": (1, "No-op baseline"), "b": (2, "Fresh Haiku"), "c": (3, "Behaviour only"),
            "d": (4, "Model only"), "e": (5, "Both")}
CONTRASTS = (("b", "a", "2 − 1  (swap alone)"), ("c", "b", "3 − 2  (behaviour only)"),
             ("d", "b", "4 − 2  (model only)"), ("e", "b", "5 − 2  (both)"))
BONFERRONI_FAMILY = 8
# Reference palette, categorical slots 1-5 in their documented order (light surface).
COLORS = {"a": "#2a78d6", "b": "#eb6834", "c": "#1baf7a", "d": "#eda100", "e": "#e87ba4"}
MARKERS = {"a": "o", "b": "s", "c": "^", "d": "D", "e": "v"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e3e2de"
MINUS = "−"


def num(x, digits=2, sign=False):
    s = f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"
    return s.replace("-", MINUS)


def ci_text(ci, digits=2):
    if ci is None:
        return "n/a"
    return f"{num(ci['mean'], digits)} [{num(ci['lo'], digits)}, {num(ci['hi'], digits)}]"


def count_text(c):
    if c is None:
        return "n/a"
    return f"{c['k']}/{c['n']} [{c['lo']:.0%}, {c['hi']:.0%}]"


def diff_text(ci, p, bold=False):
    if ci is None:
        return "n/a"
    s = f"{num(ci['diff'], 2, True)} [{num(ci['lo'], 2, True)}, {num(ci['hi'], 2, True)}]"
    ptext = "" if p is None else (", p<0.001" if p < 0.001 else f", p={p:.3f}")
    return s + ptext + (" \u2020" if bold else "")


def load(path, stable_only):
    with open(path) as f:
        data = json.load(f)
    meta = data["analysis"]["metadata"] if "analysis" in data else data["metadata"]
    swap = meta.get("swap")
    if not swap:
        raise SystemExit(f"{path}: no metadata.swap")
    rows = trial_metrics(data["rounds"], swap["agent"], swap["swap_at"])
    coop = game_rows(data["rounds"], swap["agent"], swap["swap_at"])
    if stable_only:
        keep = [i for i, c in enumerate(coop) if not c["volatile"]]
        rows, coop = [rows[i] for i in keep], [coop[i] for i in keep]
    return {"rows": rows, "coop": coop, "swap_at": swap["swap_at"], "n_rounds": len(data["rounds"])}


def build_tables(arms, n_boot):
    header1 = ["Scenario", "Final guess (1–10)", "Trust change", "Detected by the end",
               "False positive (placebo)", "Group cooperation change ‡"]
    table1 = []
    for label, a in arms.items():
        rows = a["rows"]
        ds = detection_summary(rows)
        num_, name = SCENARIO[label]
        table1.append([f"{num_}  {name}",
                       ci_text(bootstrap_ci([r["guess_score"] for r in rows], n_boot=n_boot)),
                       ci_text(bootstrap_ci([r["trust_delta"] for r in rows], n_boot=n_boot)),
                       count_text(ds["final"]), count_text(ds["placebo"]),
                       ci_text(bootstrap_ci([c["group_delta"] for c in a["coop"]], n_boot=n_boot))])

    header2 = ["Contrast", "Final guess (difference)", "Trust change (difference)"]
    table2 = []
    threshold = 0.05 / BONFERRONI_FAMILY
    for hi, lo, text in CONTRASTS:
        if hi not in arms or lo not in arms:
            continue
        cells = [text]
        for metric in ("guess_score", "trust_delta"):
            x = [r[metric] for r in arms[hi]["rows"]]
            y = [r[metric] for r in arms[lo]["rows"]]
            ci = diff_ci(x, y, n_boot=n_boot)
            p = permutation_pvalue(x, y, n_perm=n_boot)
            cells.append(diff_text(ci, p, bold=p is not None and p < threshold))
        table2.append(cells)
    if all(k in arms for k in "bcde"):
        cells = ["Interaction (5 − 4) − (3 − 2)"]
        for metric in ("guess_score", "trust_delta"):
            ci = interaction_ci(*[[r[metric] for r in arms[k]["rows"]] for k in "edcb"], n_boot=n_boot)
            cells.append("n/a" if ci is None else
                         f"{num(ci['interaction'], 2, True)} [{num(ci['lo'], 2, True)}, {num(ci['hi'], 2, True)}]")
        table2.append(cells)
    return (header1, table1), (header2, table2)


def html_table(title, header, rows, note):
    th = "".join(f"<th style='border:1px solid #999;padding:4px 8px;text-align:left;background:#f1f0ec'>{html.escape(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(
        f"<td style='border:1px solid #999;padding:4px 8px'>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows)
    return (f"<h3 style='font-family:Arial,sans-serif'>{html.escape(title)}</h3>"
            f"<table style='border-collapse:collapse;font-family:Arial,sans-serif;font-size:11pt'>"
            f"<tr>{th}</tr>{body}</table>"
            f"<p style='font-family:Arial,sans-serif;font-size:9pt;max-width:900px'>{html.escape(note)}</p>")


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def plot_figure(arms, path_png, path_pdf, n_boot):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    first = next(iter(arms.values()))
    swap_at, n_rounds = first["swap_at"], first["n_rounds"]
    rounds = list(range(swap_at, n_rounds + 1))
    n_post = n_rounds - swap_at

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": INK2,
                         "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 3.5), gridspec_kw={"wspace": 0.28})

    order = list(arms)
    for i, (label, a) in enumerate(arms.items()):
        dx = (i - (len(order) - 1) / 2) * 0.07          # small horizontal offset so intervals do not overlap
        cs = curve_summary(a["rows"], rounds, n_boot=n_boot)
        pts = [(r, cs[r]) for r in rounds if cs[r]]
        xs = [r + dx for r, _ in pts]
        means = [c["mean"] for _, c in pts]
        name = f"{SCENARIO[label][0]}  {SCENARIO[label][1]}"
        ax1.errorbar(xs, means, yerr=[[m - c["lo"] for m, (_, c) in zip(means, pts)],
                                      [c["hi"] - m for m, (_, c) in zip(means, pts)]],
                     color=COLORS[label], linewidth=2, elinewidth=1, capsize=2, marker=MARKERS[label],
                     markersize=5, markeredgecolor="white", markeredgewidth=0.8, label=name)
        share = detection_share(a["rows"], n_post)
        ax2.plot([k + dx for k in range(1, n_post + 1)], [s_ * 100 for s_ in share], color=COLORS[label],
                 marker=MARKERS[label], markersize=5, linewidth=2, markeredgecolor="white", markeredgewidth=0.8)

    ax1.axvline(swap_at + 0.5, color=INK2, linestyle="--", linewidth=1)
    ax1.text(swap_at + 0.55, 10.25, "swap", color=INK2, fontsize=8, va="bottom")
    ax1.axhline(5.5, color=INK2, linestyle=":", linewidth=1)
    ax1.text(rounds[-1] + 0.2, 5.65, "above: flagged", color=INK2, fontsize=7.5, va="bottom", ha="right")
    ax1.set_ylim(0.8, 10.8)
    ax1.set_xlim(rounds[0] - 0.2, rounds[-1] + 0.2)
    ax1.set_xticks(rounds)
    ax1.set_xticklabels([f"{r}\n(before swap)" if r == swap_at else str(r) for r in rounds])
    ax1.set_xlabel("Probe asked after round")
    ax1.set_ylabel("Peers' guess that Q was replaced (1–10)")
    ax1.set_title("a  Mean guess score", loc="left", fontsize=9.5, color=INK, fontweight="bold")

    ax2.set_ylim(-3, 103)
    ax2.set_xlim(0.8, n_post + 0.2)
    ax2.set_xticks(range(1, n_post + 1))
    ax2.set_xticklabels([f"{swap_at + k}" for k in range(1, n_post + 1)])
    ax2.set_xlabel("Round after the swap")
    ax2.set_ylabel("Games in which Q has been flagged (%)")
    ax2.set_title("b  Time to detection (cumulative)", loc="left", fontsize=9.5, color=INK, fontweight="bold")

    for ax in (ax1, ax2):
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False, fontsize=8,
               handlelength=2.2, columnspacing=1.2, bbox_to_anchor=(0.5, -0.02))
    fig.subplots_adjust(bottom=0.27, top=0.9, left=0.08, right=0.985)
    os.makedirs(os.path.dirname(path_png) or ".", exist_ok=True)
    fig.savefig(path_png, dpi=300, facecolor="white")
    fig.savefig(path_pdf, facecolor="white")


def plot_curve(arms, path_png, path_pdf, n_boot):
    """Single-panel version: mean guess score by round, with room to breathe."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    first = next(iter(arms.values()))
    swap_at, n_rounds = first["swap_at"], first["n_rounds"]
    rounds = list(range(swap_at, n_rounds + 1))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": INK2,
                         "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2})
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    order = list(arms)
    for i, (label, a) in enumerate(arms.items()):
        dx = (i - (len(order) - 1) / 2) * 0.1            # offset so the five intervals sit side by side
        cs = curve_summary(a["rows"], rounds, n_boot=n_boot)
        pts = [(r, cs[r]) for r in rounds if cs[r]]
        xs = [r + dx for r, _ in pts]
        means = [c["mean"] for _, c in pts]
        ax.errorbar(xs, means, yerr=[[m - c["lo"] for m, (_, c) in zip(means, pts)],
                                     [c["hi"] - m for m, (_, c) in zip(means, pts)]],
                    fmt="none", ecolor=COLORS[label], elinewidth=1.2, capsize=2.5, capthick=1.2,
                    alpha=0.5, zorder=2)
        ax.plot(xs, means, color=COLORS[label], linewidth=1.9, marker=MARKERS[label], markersize=6.5,
                markeredgecolor="white", markeredgewidth=0.9, label=f"{SCENARIO[label][0]}  {SCENARIO[label][1]}",
                zorder=3)

    ax.axvline(swap_at + 0.5, color=INK2, linestyle="--", linewidth=1)
    ax.text(swap_at + 0.54, 10.55, "swap", color=INK2, fontsize=9, va="bottom")
    ax.axhline(5.5, color=INK2, linestyle=":", linewidth=1)
    ax.text(rounds[-1] + 0.82, 5.65, "above this line:\nflagged", color=INK2, fontsize=8.5,
            va="bottom", ha="right", linespacing=1.15)
    ax.set_ylim(0.8, 11)
    ax.set_xlim(rounds[0] - 0.35, rounds[-1] + 0.85)
    ax.set_xticks(rounds)
    ax.set_xticklabels([f"{r}\n(before swap)" if r == swap_at else str(r) for r in rounds])
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_xlabel("Probe asked after round")
    ax.set_ylabel("Peers' guess that Q was replaced (1\u201310)")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=3, frameon=False, fontsize=9,
               handlelength=2.2, columnspacing=1.6, bbox_to_anchor=(0.5, -0.01))
    fig.subplots_adjust(bottom=0.27, top=0.95, left=0.12, right=0.98)
    fig.savefig(path_png, dpi=300, facecolor="white")
    fig.savefig(path_pdf, facecolor="white")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", required=True, help="label=path (labels a-e)")
    p.add_argument("--stable-only", action="store_true")
    p.add_argument("--out-dir", default="outputs/paper")
    p.add_argument("--n-boot", type=int, default=10000)
    args = p.parse_args()

    arms = {}
    for spec in args.arm:
        label, path = spec.split("=", 1)
        arms[label] = load(path, args.stable_only)
    sizes = {SCENARIO[k][0]: len(a["rows"]) for k, a in arms.items()}
    suffix = "_stable" if args.stable_only else ""
    os.makedirs(args.out_dir, exist_ok=True)

    (h1, t1), (h2, t2) = build_tables(arms, args.n_boot)
    games = ("Games per scenario: " + ", ".join(f"{k}: {v}" for k, v in sorted(sizes.items())) + ". ") \
        if args.stable_only else "10 games per scenario. "
    note1 = (games + "Mean over games with 95% BCa bootstrap intervals in brackets (10,000 resamples); counts are games "
             "with a guess score above 5.5, with exact (Clopper–Pearson) 95% intervals. Final guess: 1 = certain the "
             "agent is the same, 10 = certain it was replaced. Trust change: peers' trust in Q, rounds 4–6 minus "
             "rounds 1–3. False positive: share flagged at the probe asked before the swap. ‡ Exploratory: "
             "change in the share of CHEAP choices among all three agents, rounds 4–6 minus rounds 1–3.")
    note2 = (games + "Difference in means with 95% BCa bootstrap interval and two-sided permutation p. † p below "
             f"0.05/{BONFERRONI_FAMILY} (Bonferroni over 4 contrasts × 2 measures). The interaction is reported with "
             "an interval only. Scenario 2 is the baseline for the swap contrasts.")
    title_suffix = " (games with no defection before the swap)" if args.stable_only else ""
    with open(os.path.join(args.out_dir, f"tables{suffix}.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'><title>Swap results tables</title>"
                + html_table("Table 1. Results by scenario" + title_suffix, h1, t1, note1)
                + html_table("Table 2. Pre-specified contrasts" + title_suffix, h2, t2, note2))
    write_csv(os.path.join(args.out_dir, f"table1_results{suffix}.csv"), h1, t1)
    write_csv(os.path.join(args.out_dir, f"table2_contrasts{suffix}.csv"), h2, t2)
    plot_figure(arms, os.path.join(args.out_dir, f"fig_time_to_detection{suffix}.png"),
                os.path.join(args.out_dir, f"fig_time_to_detection{suffix}.pdf"), args.n_boot)
    plot_curve(arms, os.path.join(args.out_dir, f"fig_detection_curve{suffix}.png"),
               os.path.join(args.out_dir, f"fig_detection_curve{suffix}.pdf"), args.n_boot)
    print(f"Wrote tables and figure to {args.out_dir}/ (suffix '{suffix}')")
    for row in t1:
        print("  ", " | ".join(row))
    for row in t2:
        print("  ", " | ".join(row))


if __name__ == "__main__":
    main()
