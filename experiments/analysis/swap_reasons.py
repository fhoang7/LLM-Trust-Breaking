"""Code the peers' stated reasons for their same/changed guesses by the cue they cite.

Usage:
  python experiments/analysis/swap_reasons.py --arm a=run_a.json --arm b=run_b.json ... \
      [--coder-model anthropic/claude-haiku-4.5] [--no-llm] [--dump coded.json]

Uses a blind LLM coder (batched, temperature 0; it sees only the reason text, never the arm) plus a
keyword coder as a cross-check, and reports per arm, over post-swap reasons only:
  - the share of reasons citing behaviour change / style change / continuity,
  - among "changed" verdicts, the share citing behaviour vs style,
  - how often the two coders agree.
Shares are computed per trial first and summarised with a 95% BCa bootstrap CI over trials.
Results are cached next to the outputs, so re-running does not call the API again.
EXPLORATORY: these are descriptive and outside the pre-specified Bonferroni family.
"""
import argparse
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.endogenous.analysis.swap_reasons import (  # noqa: E402
    CUES, RUBRIC_VERSION, agreement, code_with_llm, extract_reasons, keyword_code, trial_cue_shares,
)
from src.endogenous.analysis.swap_stats import bootstrap_ci  # noqa: E402

CACHE_PATH = "outputs/analysis/swap_reasons_cache.json"
MEASURES = (("any_behaviour", "cites behaviour change (all reasons)"),
            ("any_style", "cites style change (all reasons)"),
            ("any_continuity", "cites continuity (all reasons)"),
            ("changed_behaviour", "among 'changed' verdicts: cites behaviour"),
            ("changed_style", "among 'changed' verdicts: cites style"),
            ("same_continuity", "among 'same' verdicts: cites continuity"))


def load_cache(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def llm_label(items, model, cache, cache_path):
    """LLM labels for items, calling the API only for reasons not already cached."""
    keys = [hashlib.sha1(f"{RUBRIC_VERSION}|{model}|{' '.join(i['reason'].split())}".encode()).hexdigest() for i in items]
    missing = sorted({k: i for k, i in zip(keys, items) if k not in cache}.items())
    if missing:
        from src.config import settings
        from src.llm.providers.queued_openrouter import QueuedOpenRouterClient
        client = QueuedOpenRouterClient(api_key=settings.OPENROUTER_API_KEY, max_workers=5,
                                        timeout=120, max_retries=5)
        print(f"  LLM coder: labelling {len(missing)} new reasons with {model}")
        fresh = code_with_llm([i for _, i in missing], client.execute_all, model=model)
        for (k, _), lab in zip(missing, fresh):
            if lab is not None:
                cache[k] = lab
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f)
    return [cache.get(k) for k in keys]


def fmt(values, n_boot):
    ci = bootstrap_ci(values, n_boot=n_boot)
    if ci is not None:
        return f"{ci['mean']:.0%} [{ci['lo']:.0%}, {ci['hi']:.0%}] (n={ci['n']} trials)"
    present = [v for v in values if v is not None]
    return "n/a" if not present else f"{sum(present) / len(present):.0%} ({len(present)} trial, no interval)"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", action="append", required=True, help="label=path")
    p.add_argument("--coder-model", default="anthropic/claude-haiku-4.5")
    p.add_argument("--no-llm", action="store_true", help="keyword coder only (no API calls)")
    p.add_argument("--cache", default=CACHE_PATH)
    p.add_argument("--dump", default=None, help="write every reason with both coders' labels to this JSON")
    p.add_argument("--n-boot", type=int, default=10000)
    args = p.parse_args()

    cache = load_cache(args.cache)
    dump = {}
    for spec in args.arm:
        label, path = spec.split("=", 1)
        with open(path) as f:
            data = json.load(f)
        meta = data["analysis"]["metadata"] if "analysis" in data else data["metadata"]
        swap = meta.get("swap")
        if not swap:
            raise SystemExit(f"{path}: no metadata.swap")
        items = extract_reasons(data["rounds"], swap["swap_at"])
        n_trials = len(data["rounds"][0]["trials"])
        kw = [keyword_code(i["reason"]) for i in items]
        llm = [None] * len(items) if args.no_llm else llm_label(items, args.coder_model, cache, args.cache)
        main_labels = kw if args.no_llm else llm
        shares = trial_cue_shares(items, main_labels, n_trials)
        post = [i for i in items if i["phase"] == "post"]

        print(f"\n=== arm {label}: {len(items)} reasons ({len(post)} post-swap), "
              f"coder: {'keywords only' if args.no_llm else args.coder_model}")
        for key, text in MEASURES:
            print(f"  {text}: {fmt([s[key] for s in shares], args.n_boot)}")
        if not args.no_llm:
            ag = agreement(llm, kw)
            print(f"  coder agreement (LLM vs keywords, n={ag['n']}): " +
                  ", ".join(f"{c} {ag[c]:.0%}" for c in CUES if ag[c] is not None))
        rng = random.Random(0)
        for it in rng.sample(post, min(2, len(post))):
            print(f"  e.g. [{it['guess']} {it['confidence']}, round {it['round']}] {it['reason'][:160]}")
        dump[label] = [dict(it, llm=l, keywords=k) for it, l, k in zip(items, llm, kw)]

    if args.dump:
        os.makedirs(os.path.dirname(args.dump) or ".", exist_ok=True)
        with open(args.dump, "w") as f:
            json.dump(dump, f, indent=1)
        print(f"\nWrote {args.dump}")


if __name__ == "__main__":
    main()
