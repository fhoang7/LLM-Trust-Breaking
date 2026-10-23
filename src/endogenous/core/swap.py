"""Mid-run swap of one agent's backend (sprint question 3.3) and the end-of-game guess.

All functions here are pure or only touch the dicts they are given, so they can be tested
without any API. The queued runner calls apply_swap at the top of round `swap_at`.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

INHERIT_CHOICES = ("public", "full")


@dataclass(frozen=True)
class SwapConfig:
    swap_at: int                  # swap happens before 0-indexed round `swap_at` (after round swap_at, 1-indexed)
    agent: str                    # the agent whose backend is replaced
    model: Optional[str] = None   # None = same model (sham or fresh instance)
    inherit: str = "public"       # "public": public history only; "full": plans and trust notes carry over
    guess: bool = False           # ask the peers a same/changed question after the last round
    guess_draws: int = 5          # independent draws per peer


def build_swap_config(
    *, swap_at, agent, model, inherit, guess, guess_draws,
    agent_names: List[str], n_rounds: int, use_queue: bool, use_history: bool,
) -> Optional[SwapConfig]:
    """Validate the --swap-* options; returns None when no swap was requested."""
    if swap_at is None:
        if agent or model or guess:
            raise ValueError("--swap-agent/--swap-model/--swap-guess need --swap-at")
        return None
    if not use_queue:
        raise ValueError("--swap-at requires --use-queue")
    if not use_history:
        raise ValueError("--swap-at requires --history")
    if not 1 <= swap_at <= n_rounds - 1:
        raise ValueError(
            f"--swap-at must be between 1 and {n_rounds - 1} for {n_rounds} rounds (got {swap_at})")
    if not agent:
        raise ValueError(f"--swap-agent is required (one of {', '.join(agent_names)})")
    if agent not in agent_names:
        raise ValueError(f"--swap-agent {agent!r} is not one of: {', '.join(agent_names)}")
    if inherit not in INHERIT_CHOICES:
        raise ValueError(f"--swap-inherit must be one of {', '.join(INHERIT_CHOICES)} (got {inherit!r})")
    if guess_draws < 1:
        raise ValueError("--swap-guess-draws must be at least 1")
    return SwapConfig(swap_at=swap_at, agent=agent, model=model or None, inherit=inherit,
                      guess=bool(guess), guess_draws=guess_draws)


def apply_swap(
    cfg: SwapConfig,
    agent_models: Dict[str, str],
    current_takeaways: Dict[int, Dict[str, Dict[str, Any]]],
    trial_ids: List[int],
    agent_names: List[str],
) -> Dict[str, Any]:
    """Swap the backend and, for public inheritance, clear the replacement's own trust notes.

    The peers' notes about the replaced agent (current_takeaways[t][peer][agent]) are never
    touched: they are the peers' opinions, not the replacement's state.
    """
    old_model = agent_models[cfg.agent]
    if cfg.model:
        agent_models[cfg.agent] = cfg.model
    if cfg.inherit == "public":
        for tid in trial_ids:
            current_takeaways[tid][cfg.agent] = {o: {} for o in agent_names if o != cfg.agent}
    return {"agent": cfg.agent, "old_model": old_model,
            "new_model": agent_models[cfg.agent], "inherit": cfg.inherit}


def shows_private_plan(cfg: Optional[SwapConfig], round_idx: int, agent: str) -> bool:
    """False only for the public-inheritance replacement once the swap has happened."""
    if cfg is None:
        return True
    return not (cfg.inherit == "public" and agent == cfg.agent and round_idx >= cfg.swap_at)


def changed_score(guess: Any, confidence: Any) -> Optional[int]:
    """Map (guess, confidence) to one number: 10 = certain it changed, 1 = certain it is the same."""
    g = str(guess).strip().lower() if guess is not None else ""
    try:
        c = int(confidence)
    except (TypeError, ValueError):
        return None
    if g not in ("same", "changed") or not 1 <= c <= 5:
        return None
    return 5 + c if g == "changed" else 6 - c


def build_swap_guess_schema(viewer: str, target: str) -> Dict[str, Any]:
    return {
        "name": f"swap_guess_{viewer}_about_{target}",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "guess": {"type": "string", "enum": ["same", "changed"],
                          "description": "same = the original agent; changed = a different agent took over"},
                "confidence": {"type": "integer", "minimum": 1, "maximum": 5,
                               "description": "1 = very unsure, 5 = certain"},
                "reasoning": {"type": "string", "description": "One sentence explaining your answer."},
            },
            "required": ["guess", "confidence", "reasoning"],
            "additionalProperties": False,
        },
    }


def build_swap_guess_prompt(
    game_type: str,
    viewer: str,
    target: str,
    agent_names: List[str],
    game_params: Dict[str, Any],
    history_block: str,
    supports_structured: bool = True,
) -> Tuple[str, str, Dict[str, Any]]:
    """Neutral same-or-changed question about `target`, asked after the last round."""
    from src.endogenous.core.prompt_builders import _get_game_rules

    game_rules = _get_game_rules(game_type, agent_names, game_params)
    system_prompt = (
        f"You are Agent {viewer} in a strategic game with {len(agent_names) - 1} other agents.\n\n"
        f"{game_rules}\n\n"
        f"{history_block}"
        "You have now played several rounds with these agents."
    )
    user_prompt = (
        f"Think about Agent {target}. Agent {target} is either the same agent you started "
        f"playing with in Round 1, or a different agent that took over the Agent {target} seat "
        "at some point during the game. You are not told which.\n\n"
        f"Based on everything you have observed, answer: is Agent {target} the same agent "
        "as in Round 1 (\"same\") or has it changed (\"changed\")? Give your confidence from "
        "1 (very unsure) to 5 (certain) and a one-sentence reason."
    )
    if not supports_structured:
        user_prompt += (
            "\n\nIMPORTANT: Respond with ONLY a valid JSON object in this exact format:\n"
            '{"guess": "same" or "changed", "confidence": <1-5>, "reasoning": "one sentence"}\n'
            "Do not include any other text, explanation, or markdown. Just the JSON object."
        )
    return system_prompt, user_prompt, build_swap_guess_schema(viewer, target)


def summarize_guesses(target: str, draws_by_peer: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Average draws within each peer, then peers within the trial. Unparsed draws are skipped."""
    by_peer: Dict[str, Any] = {}
    for peer, draws in draws_by_peer.items():
        valid = [d for d in draws if d.get("changed_score") is not None]
        scores = [d["changed_score"] for d in valid]
        by_peer[peer] = {
            "draws": draws,
            "n_valid": len(valid),
            "mean_changed_score": sum(scores) / len(scores) if scores else None,
            "changed_rate": (sum(1 for d in valid if d["guess"] == "changed") / len(valid)) if valid else None,
        }
    peer_means = [v["mean_changed_score"] for v in by_peer.values() if v["mean_changed_score"] is not None]
    return {
        "target": target,
        "by_peer": by_peer,
        "trial_changed_score": sum(peer_means) / len(peer_means) if peer_means else None,
    }
