import json
import unittest

from src.endogenous.analysis.swap_reasons import (
    agreement, code_with_llm, extract_reasons, keyword_code, parse_coder_output, trial_cue_shares,
)

CHANGED_BEHAVIOUR = ("Agent Q's behavior fundamentally shifted in Round 4 from perfect cooperation to "
                     "defection, a reversal so complete that it suggests a different agent took over")
CONTINUITY = ("Agent Q's messaging shows consistent character development with no sudden shifts in "
              "personality or values that would suggest agent replacement")
STYLE = "The wording and phrasing in Q's recent announcements differ noticeably from its earlier style"


def draw(guess, conf, reason):
    return {"guess": guess, "confidence": conf, "reason": reason, "changed_score": 7, "_parse_ok": True}


def fake_rounds():
    """2 trials, 4 rounds, swap after round 2 -> guesses after rounds 2 (placebo), 3 and 4."""
    rounds = []
    for r in range(4):
        trials = []
        for tid in range(2):
            t = {"trial_id": tid, "agents": {}}
            if r >= 1:
                t["swap_guess"] = {"target": "Q", "by_peer": {
                    "J": {"draws": [draw("changed" if tid == 0 else "same", 4,
                                         CHANGED_BEHAVIOUR if tid == 0 else CONTINUITY),
                                    draw("same", 3, CONTINUITY)]},
                    "M": {"draws": [draw("changed", 5, STYLE)]},
                }}
            trials.append(t)
        rounds.append({"round_id": r, "trials": trials})
    return rounds


class KeywordCoderTests(unittest.TestCase):
    def test_behaviour_change(self):
        c = keyword_code(CHANGED_BEHAVIOUR)
        self.assertTrue(c["behaviour"])
        self.assertFalse(c["continuity"])

    def test_continuity_with_negated_change_words_is_not_behaviour(self):
        c = keyword_code(CONTINUITY)
        self.assertTrue(c["continuity"])
        self.assertFalse(c["behaviour"])

    def test_style_change(self):
        c = keyword_code(STYLE)
        self.assertTrue(c["style"])
        self.assertFalse(c["behaviour"])

    def test_empty_text_has_no_cues(self):
        self.assertEqual(keyword_code(""), {"behaviour": False, "style": False, "continuity": False})


class ExtractTests(unittest.TestCase):
    def test_extracts_every_draw_with_round_phase_and_trial(self):
        items = extract_reasons(fake_rounds(), swap_at=2)
        self.assertEqual(len(items), 2 * 3 * 3)               # 2 trials x 3 guess rounds x (2 + 1) draws
        first = items[0]
        self.assertEqual((first["trial"], first["round"], first["phase"], first["peer"]), (0, 2, "pre", "J"))
        self.assertEqual({i["phase"] for i in items if i["round"] >= 3}, {"post"})
        self.assertIn("reason", first)
        self.assertEqual(first["guess"], "changed")

    def test_runs_without_guess_data_give_nothing(self):
        rounds = [{"round_id": 0, "trials": [{"trial_id": 0, "agents": {}}]}]
        self.assertEqual(extract_reasons(rounds, swap_at=1), [])


class ParseTests(unittest.TestCase):
    def test_parses_labels_in_order_and_marks_missing(self):
        content = json.dumps({"labels": [
            {"i": 1, "behaviour": True, "style": False, "continuity": False},
            {"i": 3, "behaviour": False, "style": True, "continuity": True},
        ]})
        out = parse_coder_output(content, 3)
        self.assertEqual(out[0], {"behaviour": True, "style": False, "continuity": False})
        self.assertIsNone(out[1])
        self.assertEqual(out[2], {"behaviour": False, "style": True, "continuity": True})

    def test_handles_code_fences_and_garbage(self):
        fenced = "```json\n" + json.dumps({"labels": [{"i": 1, "behaviour": True, "style": False,
                                                          "continuity": False}]}) + "\n```"
        self.assertTrue(parse_coder_output(fenced, 1)[0]["behaviour"])
        self.assertEqual(parse_coder_output("not json at all", 2), [None, None])
        self.assertEqual(parse_coder_output(None, 1), [None])


class LlmCoderTests(unittest.TestCase):
    def test_batches_requests_and_returns_labels_in_item_order(self):
        items = [{"reason": f"r{i}"} for i in range(5)]
        seen = []

        def execute(requests):
            out = {}
            for req in requests:
                seen.append(req)
                text = req["messages"][1]["content"]
                n = text.count("\n") + 1
                # label item k of this batch as behaviour iff its number is odd
                labels = [{"i": k, "behaviour": k % 2 == 1, "style": False, "continuity": False}
                          for k in range(1, n + 1)]
                out[req["custom_id"]] = {"content": json.dumps({"labels": labels})}
            return out

        labels = code_with_llm(items, execute, model="m/x", batch_size=2)
        self.assertEqual(len(seen), 3)                              # 2 + 2 + 1
        self.assertTrue(all(r["temperature"] == 0 and r["model"] == "m/x" for r in seen))
        self.assertEqual([l["behaviour"] for l in labels], [True, False, True, False, True])

    def test_prompt_never_mentions_arms_or_swap_conditions(self):
        seen = []
        code_with_llm([{"reason": "x"}], lambda reqs: seen.extend(reqs) or {}, model="m/x")
        text = json.dumps(seen[0]["messages"]).lower()
        for word in ("arm", "sham", "deepseek", "forced", "haiku"):
            self.assertNotIn(word, text)

    def test_failed_batch_gives_none(self):
        labels = code_with_llm([{"reason": "x"}], lambda reqs: {r["custom_id"]: {"error": "boom"} for r in reqs},
                               model="m/x")
        self.assertEqual(labels, [None])


class SharesTests(unittest.TestCase):
    def test_per_trial_shares_over_post_swap_reasons(self):
        items = extract_reasons(fake_rounds(), swap_at=2)
        labels = [keyword_code(i["reason"]) for i in items]
        shares = trial_cue_shares(items, labels, n_trials=2)
        # trial 0 post-swap: per round J changed(behaviour), J same(continuity), M changed(style)
        self.assertEqual(shares[0]["n_post"], 6)
        self.assertAlmostEqual(shares[0]["any_behaviour"], 2 / 6)
        self.assertAlmostEqual(shares[0]["any_style"], 2 / 6)
        self.assertAlmostEqual(shares[0]["any_continuity"], 2 / 6)
        self.assertEqual(shares[0]["changed_n"], 4)                 # J and M verdicts of "changed"
        self.assertAlmostEqual(shares[0]["changed_behaviour"], 2 / 4)
        self.assertAlmostEqual(shares[0]["changed_style"], 2 / 4)
        # trial 1: J says same with continuity, plus M's style-based "changed" verdict
        self.assertEqual(shares[1]["changed_n"], 2)

    def test_pre_swap_reasons_are_excluded_and_unlabelled_items_skipped(self):
        items = extract_reasons(fake_rounds(), swap_at=2)
        labels = [None] * len(items)
        shares = trial_cue_shares(items, labels, n_trials=2)
        self.assertIsNone(shares[0]["any_behaviour"])
        self.assertEqual(shares[0]["n_post"], 0)


class AgreementTests(unittest.TestCase):
    def test_percent_agreement_per_cue(self):
        a = [{"behaviour": True, "style": False, "continuity": False}, {"behaviour": False, "style": False, "continuity": True}]
        b = [{"behaviour": True, "style": True, "continuity": False}, {"behaviour": True, "style": False, "continuity": True}]
        out = agreement(a, b)
        self.assertEqual(out["behaviour"], 0.5)
        self.assertEqual(out["style"], 0.5)
        self.assertEqual(out["continuity"], 1.0)
        self.assertEqual(out["n"], 2)

    def test_skips_items_either_coder_missed(self):
        a = [None, {"behaviour": True, "style": False, "continuity": False}]
        b = [{"behaviour": True, "style": False, "continuity": False}, {"behaviour": True, "style": False, "continuity": False}]
        self.assertEqual(agreement(a, b)["n"], 1)


if __name__ == "__main__":
    unittest.main()
