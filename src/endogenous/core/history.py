"""Per-agent history of earlier rounds, rendered into prompts (opt-in via --history).

Records hold only information that is public after a round (announcements, final
choices, payoffs) plus every agent's own intended action. build_history_block shows
a viewer only its own plan. Reasoning text is never stored.
"""
from typing import Any, Dict, List


def make_round_record(
    round_idx: int,
    plans: Dict[str, Any],
    announcements: Dict[str, Dict[str, Any]],
    outcomes: Dict[str, Any],
) -> Dict[str, Any]:
    """Snapshot one completed round.

    plans:         agent -> intended_action (stage 1)
    announcements: agent -> {"stated_action", "message"} (stage 2); other keys are dropped
    outcomes:      {"choices": {...}, "payoffs": {...}} as returned by _compute_outcomes
    """
    return {
        "round_id": round_idx,
        "plans": dict(plans),
        "announcements": {
            agent: {"stated_action": a.get("stated_action"), "message": a.get("message", "")}
            for agent, a in announcements.items()
        },
        "choices": dict(outcomes.get("choices", {})),
        "payoffs": dict(outcomes.get("payoffs", {})),
    }


def _choice(value: Any) -> str:
    return "unknown" if value is None else str(value)


def _payoff(value: Any) -> str:
    return f"{value:.1f}" if isinstance(value, (int, float)) else "n/a"


def build_history_block(agent_name: str, rounds: List[Dict[str, Any]]) -> str:
    """Render the history one agent may see; "" when there are no earlier rounds."""
    if not rounds:
        return ""
    lines = ["HISTORY OF PREVIOUS ROUNDS (what you have observed so far):"]
    for rec in rounds:
        lines.append(f"Round {rec['round_id'] + 1}:")
        lines.append(f"  Your private plan: {_choice(rec['plans'].get(agent_name))}")
        for name, ann in rec["announcements"].items():
            who = f"Agent {name} (you)" if name == agent_name else f"Agent {name}"
            lines.append(f'  {who} announced {_choice(ann["stated_action"])}: "{ann["message"]}"')
        results = "; ".join(
            f"Agent {name} chose {_choice(choice)} and earned {_payoff(rec['payoffs'].get(name))}"
            for name, choice in rec["choices"].items()
        )
        lines.append(f"  Final choices: {results}")
    return "\n".join(lines) + "\n\n"
