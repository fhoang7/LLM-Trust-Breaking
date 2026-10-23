"""Code the peers' stated reasons for their same/changed guesses by the cue they cite.

Every guess draw stores a one-sentence reason. This module labels each reason with three cues
(a reason can cite more than one):

  behaviour   a change in what Q did (started defecting, broke a promise, reversed course)
  style       a change in Q's wording, tone, vocabulary or reasoning style
  continuity  consistency or the absence of change, offered as grounds for "same"

Two coders: a blind LLM coder (batched, temperature 0, sees only the reasons) and a keyword coder
used as a cross-check. Nothing here knows which arm a reason came from.
"""
import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

CUES = ("behaviour", "style", "continuity")

_CHANGE = (r"(?:sudden\w*|abrupt\w*|shift\w*|chang\w*|deviat\w*|defect\w*|betray\w*|break\w*|broke\w*|"
           r"reversal\w*|differ\w*)")
# "no sudden shifts", "without any abrupt change", "rather than the abrupt shift": a negated change
_NEGATED_CHANGE = re.compile(
    r"\b(?:no|not|never|without|nor|rather than|instead of|absence of|lack of)\b[^.;]{0,40}?"
    + _CHANGE + r"(?:\s+" + _CHANGE + r")*")
_BEHAVIOUR = re.compile(
    r"defect|betray|broke|break|deviat|reversal|contradict|expensive|abrupt|sudden")
_STYLE = re.compile(
    r"wording|phrasing|vocabular|\bstyle|\btone\b|\bvoice\b|writing|linguistic|rhetoric|diction|"
    r"word choice|sentence")
_CONTINUITY = re.compile(
    r"consisten|continu|steady|steadfast|\bstable\b|same agent|coheren|evolv|unwaver")
_CHANGE_ANY = re.compile(_CHANGE)


def keyword_code(reason: Optional[str]) -> Dict[str, bool]:
    """Rough rule-based labels, used only as a cross-check on the LLM coder."""
    text = (reason or "").lower()
    cleaned = _NEGATED_CHANGE.sub(" ", text)
    had_negated_change = cleaned != text
    continuity = bool(_CONTINUITY.search(text)) or had_negated_change
    behaviour = bool(_BEHAVIOUR.search(cleaned))
    # A style word only counts as a cited *change* when the text also names a change
    # or does not otherwise present itself as continuity.
    style = bool(_STYLE.search(cleaned)) and (bool(_CHANGE_ANY.search(cleaned)) or not continuity)
    return {"behaviour": behaviour, "style": style, "continuity": continuity}


def extract_reasons(rounds: List[Dict[str, Any]], swap_at: int) -> List[Dict[str, Any]]:
    """Every stored guess draw as a flat record.

    round is 1-indexed; phase is "pre" for the guess asked before any swap (round == swap_at,
    the placebo) and "post" afterwards.
    """
    items = []
    for r, rnd in enumerate(rounds):
        for trial in rnd["trials"]:
            guess = trial.get("swap_guess")
            if not guess:
                continue
            for peer, data in guess["by_peer"].items():
                for k, d in enumerate(data["draws"]):
                    items.append({
                        "trial": trial["trial_id"], "round": r + 1,
                        "phase": "pre" if r + 1 <= swap_at else "post",
                        "peer": peer, "draw": k, "guess": d.get("guess"),
                        "confidence": d.get("confidence"), "reason": d.get("reason") or "",
                    })
    return items


RUBRIC_VERSION = "v2"     # part of the cache key: change it whenever the instructions below change

_SYSTEM = (
    "You label short explanations that one player in a repeated game gave for judging whether "
    "another player's seat was taken over by a different agent. For each numbered explanation, "
    "decide which of these cues it cites as a reason to think the player CHANGED. An explanation "
    "may cite several cues, or none:\n"
    "- behaviour: it points to a CHANGE in what the other player did (started defecting, broke a "
    "promise, reversed course, chose differently from before). Saying that its actions have "
    "stayed the same does NOT count.\n"
    "- style: it points to a CHANGE in the other player's wording, tone, vocabulary or way of "
    "reasoning. Saying that its wording or style has stayed the same does NOT count.\n"
    "- continuity: it points to consistency or the absence of change (in actions, wording or "
    "anything else) as grounds for thinking it is the same player.\n"
    "Examples: 'suddenly started defecting after three cooperative rounds' -> behaviour only. "
    "'The phrasing is noticeably different from earlier rounds' -> style only. "
    "'Consistent vocabulary and no sudden shifts in values' -> continuity only (behaviour and "
    "style are false because no change is cited). 'Cooperated throughout, same voice as before' "
    "-> continuity only.\n"
    "Judge only what the explanation says. Reply with ONLY a JSON object of the form "
    '{"labels": [{"i": 1, "behaviour": true, "style": false, "continuity": false}, ...]} '
    "with one entry per numbered explanation."
)


def build_coder_messages(reasons: Sequence[str]) -> List[Dict[str, str]]:
    lines = [f"{i}. " + " ".join(str(r).split()) for i, r in enumerate(reasons, start=1)]
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def parse_coder_output(content: Any, n: int) -> List[Optional[Dict[str, bool]]]:
    """Labels in item order; None where the coder's answer is missing or unreadable."""
    out: List[Optional[Dict[str, bool]]] = [None] * n
    if isinstance(content, dict):
        data = content
    else:
        text = str(content or "").strip()
        if "```" in text:
            text = text.split("```json")[1].split("```")[0] if "```json" in text else text.split("```")[1]
        try:
            data = json.loads(text.strip())
        except (json.JSONDecodeError, ValueError, IndexError):
            return out
    for entry in (data.get("labels") or []) if isinstance(data, dict) else []:
        try:
            i = int(entry["i"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n:
            out[i] = {cue: bool(entry.get(cue, False)) for cue in CUES}
    return out


def code_with_llm(items: Sequence[Dict[str, Any]], execute: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
                  model: str, batch_size: int = 10) -> List[Optional[Dict[str, bool]]]:
    """Label items in batches. `execute(requests)` maps custom_id -> response (dict with 'content')."""
    requests, spans = [], []
    for b, start in enumerate(range(0, len(items), batch_size)):
        chunk = items[start:start + batch_size]
        requests.append({"custom_id": f"code_{b}", "model": model, "temperature": 0, "max_tokens": 1500,
                         "messages": build_coder_messages([c["reason"] for c in chunk])})
        spans.append((f"code_{b}", start, len(chunk)))
    responses = execute(requests) if requests else {}
    labels: List[Optional[Dict[str, bool]]] = [None] * len(items)
    for cid, start, n in spans:
        resp = responses.get(cid) or {}
        if not isinstance(resp, dict) or "error" in resp:
            continue
        content = resp.get("content", resp if "labels" in resp else None)
        for j, lab in enumerate(parse_coder_output(content, n)):
            labels[start + j] = lab
    return labels


def _share(flags: List[bool]) -> Optional[float]:
    return sum(flags) / len(flags) if flags else None


def trial_cue_shares(items: Sequence[Dict[str, Any]], labels: Sequence[Optional[Dict[str, bool]]],
                     n_trials: int) -> List[Dict[str, Optional[float]]]:
    """Per trial, over post-swap reasons that were labelled.

    any_<cue>: share of all post-swap reasons citing the cue. changed_<cue>: among reasons whose
    verdict was "changed", the share citing it. same_continuity: among "same" verdicts, the share
    citing continuity. The trial is the unit, as everywhere else.
    """
    per_trial: List[Dict[str, Any]] = [{"all": [], "changed": [], "same": []} for _ in range(n_trials)]
    for item, lab in zip(items, labels):
        if lab is None or item["phase"] != "post":
            continue
        bucket = per_trial[item["trial"]]
        bucket["all"].append(lab)
        if item["guess"] == "changed":
            bucket["changed"].append(lab)
        elif item["guess"] == "same":
            bucket["same"].append(lab)
    out = []
    for b in per_trial:
        row: Dict[str, Optional[float]] = {"n_post": len(b["all"]), "changed_n": len(b["changed"]),
                                           "same_n": len(b["same"])}
        for cue in CUES:
            row[f"any_{cue}"] = _share([lab[cue] for lab in b["all"]])
        row["changed_behaviour"] = _share([lab["behaviour"] for lab in b["changed"]])
        row["changed_style"] = _share([lab["style"] for lab in b["changed"]])
        row["same_continuity"] = _share([lab["continuity"] for lab in b["same"]])
        out.append(row)
    return out


def agreement(a: Sequence[Optional[Dict[str, bool]]], b: Sequence[Optional[Dict[str, bool]]]) -> Dict[str, Any]:
    """Share of items on which two coders give the same answer, per cue (items both labelled)."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    out: Dict[str, Any] = {"n": len(pairs)}
    for cue in CUES:
        out[cue] = sum(x[cue] == y[cue] for x, y in pairs) / len(pairs) if pairs else None
    return out
