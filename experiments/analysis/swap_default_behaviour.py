"""Appendix table: how the two models behave by default when free to choose.

Usage:
  python experiments/analysis/swap_default_behaviour.py --arm a=run_a.json --arm b=... --arm e=... \
      [--arm c=... --arm d=...] [--out-dir outputs/paper]

Compares Q's choices after the swap in the scenarios where Q chooses freely: the Haiku replacement
(scenarios 1 and 2) against the DeepSeek replacement (scenario 5). The forced-choice scenarios (3, 4)
are excluded, because Q's choice there is set by the experiment. Also gives the Haiku peers' (J and M)
choices before any swap as a reference. The game is the unit; intervals are 95% percentile bootstrap
over games, and proportions use exact (Clopper-Pearson) intervals. Exploratory and untested.

Writes table_default_behaviour.html / .csv / .docx.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.endogenous.analysis.swap_stats import bootstrap_ci, diff_ci, exact_binomial_ci  # noqa: E402
from swap_paper_outputs import SCENARIO, MINUS, ci_text, count_text, html_table, num, write_csv, write_docx  # noqa: E402

COOPERATIVE = "CHEAP"


def cheap_share(rounds, agents, round_range):
    """Per game: share of the given agents' final choices in the given rounds that were CHEAP."""
    out = []
    for t in range(len(rounds[0]["trials"])):
        flags = []
        for r in round_range:
            for name in agents(rounds[r]["trials"][t]):
                choice = rounds[r]["trials"][t]["agents"][name]["stage3"].get("choice")
                if choice is not None:
                    flags.append(choice == COOPERATIVE)
        out.append(sum(flags) / len(flags) if flags else None)
    return out


def load(path):
    with open(path) as f:
        data = json.load(f)
    meta = data["analysis"]["metadata"] if "analysis" in data else data["metadata"]
    swap = meta.get("swap")
    if not swap:
        raise SystemExit(f"{path}: no metadata.swap")
    return data["rounds"], swap


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", required=True, help="label=path (labels a-e)")
    p.add_argument("--out-dir", default="outputs/paper")
    p.add_argument("--n-boot", type=int, default=10000)
    args = p.parse_args()

    runs = {}
    for spec in args.arm:
        label, path = spec.split("=", 1)
        runs[label] = load(path)
    for needed in ("a", "b", "e"):
        if needed not in runs:
            raise SystemExit(f"need scenarios a, b and e (got {sorted(runs)})")
    swap_at = runs["a"][1]["swap_at"]
    n_rounds = len(runs["a"][0])
    post, pre = range(swap_at, n_rounds), range(0, swap_at)
    q = lambda trial: [runs["a"][1]["agent"]]                      # the swapped agent
    q_post = {k: cheap_share(runs[k][0], q, post) for k in "abe"}
    haiku_pooled = q_post["a"] + q_post["b"]

    def expensive_games(shares):
        flags = [s < 1 for s in shares if s is not None]
        return exact_binomial_ci(sum(flags), len(flags))

    header = ["Q after the swap (free to choose)", "Games",
              f"Share of CHEAP choices, rounds {swap_at + 1}–{n_rounds}: mean [95% CI]",
              "Proportion of games with at least one EXPENSIVE choice [exact 95% CI]"]
    rows = []
    for label, text, shares in (("a", "Haiku (scenario 1, no-op)", q_post["a"]),
                                ("b", "Haiku (scenario 2, fresh instance)", q_post["b"]),
                                (None, "Haiku, scenarios 1 and 2 pooled", haiku_pooled),
                                ("e", "DeepSeek (scenario 5)", q_post["e"])):
        rows.append([text, str(len(shares)), ci_text(bootstrap_ci(shares, n_boot=args.n_boot)),
                     count_text(expensive_games(shares))])
    d = diff_ci(q_post["e"], haiku_pooled, n_boot=args.n_boot)
    rows.append(["Difference: DeepSeek − Haiku (pooled)", "–",
                 f"{num(d['diff'], 2, True)} [{num(d['lo'], 2, True)}, {num(d['hi'], 2, True)}]", "–"])

    peers = []
    for k, (rounds, _) in runs.items():
        peers += cheap_share(rounds, lambda trial: [n for n in trial["agents"] if n != runs["a"][1]["agent"]], pre)
    rows.append([f"Reference: Haiku peers (J and M), rounds 1–{swap_at}, before any swap, all scenarios",
                 str(len([s for s in peers if s is not None])),
                 ci_text(bootstrap_ci(peers, n_boot=args.n_boot)), "–"])

    note = (f"The swapped agent's final choices after the swap, in the scenarios where it chooses freely (the "
            f"forced-choice scenarios 3 and 4 are excluded because its choice is set by the experiment). For each game, "
            f"the share of its choices in rounds {swap_at + 1}–{n_rounds} that were CHEAP, the cooperative option; "
            f"means over games with 95% percentile bootstrap intervals (10,000 resamples). Proportions carry exact "
            f"(Clopper–Pearson) 95% intervals. The last row is the share of CHEAP choices by the two Haiku peers before "
            f"any swap, pooled over every game and scenario. Exploratory; no significance test. DeepSeek plays among "
            f"Haiku peers, who may change their own behaviour in response to it.")
    title = "Table A1. Default behaviour of the two models when free to choose"

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "table_default_behaviour.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'><title>Default behaviour</title>"
                + html_table(title, header, rows, note))
    write_csv(os.path.join(args.out_dir, "table_default_behaviour.csv"), header, rows)
    write_docx(os.path.join(args.out_dir, "table_default_behaviour.docx"), [(title, header, rows, note)])
    print(f"Wrote {title}")
    for r in rows:
        print("  ", " | ".join(r))


if __name__ == "__main__":
    main()
