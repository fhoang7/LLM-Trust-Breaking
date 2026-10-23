import unittest

from src.endogenous.analysis.swap_stats import (
    bootstrap_ci, curve_summary, detection_share, detection_summary, diff_ci,
    exact_binomial_ci, interaction_ci, paper_metrics, permutation_pvalue, trial_metrics,
)


def agent(stated, choice, takeaways=None):
    out = {"stage2": {"stated_action": stated}, "stage3": {"choice": choice}}
    if takeaways is not None:
        out["reflection"] = {"takeaways": {t: {"score": s, "assessment": "a"} for t, s in takeaways.items()}}
    return out


def fake_rounds():
    """One trial, 4 rounds, agents J M Q, swap of Q after round 2.

    Pre (rounds 0-1): J and M trust Q at 5, always keep promises and choose CHEAP.
    Post (rounds 2-3): J and M trust Q at 3; J starts announcing CHEAP but choosing EXPENSIVE.
    """
    rounds = []
    for r in range(4):
        post = r >= 2
        trust_q = 3 if post else 5
        j = agent("CHEAP", "EXPENSIVE" if post else "CHEAP", {"Q": trust_q, "M": 5})
        m = agent("CHEAP", "CHEAP", {"Q": trust_q, "J": 5})
        q = agent("CHEAP", "CHEAP", {"J": 1, "M": 1})   # Q's own opinions must be ignored
        trial = {"trial_id": 0, "agents": {"J": j, "M": m, "Q": q}}
        rounds.append({"round_id": r, "trials": [trial]})
    # guesses after rounds idx 1 (placebo, the last round before the swap), 2 and 3
    for idx, score in ((1, 1.5), (2, 4.0), (3, 7.5)):
        rounds[idx]["trials"][0]["swap_guess"] = {"trial_changed_score": score}
    return rounds


class TrialMetricsTests(unittest.TestCase):
    def test_metrics_for_a_known_game(self):
        m = trial_metrics(fake_rounds(), swap_agent="Q", swap_at=2)[0]
        self.assertEqual(m["guess_score"], 7.5)
        self.assertAlmostEqual(m["trust_delta"], 3 - 5)               # peers' trust in Q: 5 -> 3
        # incumbents J,M: CHEAP rate pre 1.0; post J:0 M:1 -> 0.5
        self.assertAlmostEqual(m["coop_delta"], 0.5 - 1.0)
        # announce-vs-choose gap pre 0.0; post J differs, M does not -> 0.5
        self.assertAlmostEqual(m["gap_delta"], 0.5 - 0.0)

    def test_guess_curve_placebo_and_time_to_detection(self):
        m = trial_metrics(fake_rounds(), swap_agent="Q", swap_at=2)[0]
        self.assertEqual(m["guess_curve"], {2: 1.5, 3: 4.0, 4: 7.5})   # keyed by 1-indexed round
        self.assertEqual(m["placebo_score"], 1.5)
        self.assertEqual(m["time_to_detection"], 2)    # first detected in the 2nd post-swap round

    def test_never_detected_gives_none(self):
        rounds = fake_rounds()
        rounds[3]["trials"][0]["swap_guess"] = {"trial_changed_score": 5.0}
        self.assertIsNone(trial_metrics(rounds, "Q", 2)[0]["time_to_detection"])

    def test_detection_in_the_placebo_round_does_not_count(self):
        rounds = fake_rounds()
        rounds[1]["trials"][0]["swap_guess"] = {"trial_changed_score": 9.0}
        rounds[2]["trials"][0]["swap_guess"] = {"trial_changed_score": 3.0}
        rounds[3]["trials"][0]["swap_guess"] = {"trial_changed_score": 3.0}
        m = trial_metrics(rounds, "Q", 2)[0]
        self.assertEqual(m["placebo_score"], 9.0)
        self.assertIsNone(m["time_to_detection"])

    def test_missing_pieces_give_none(self):
        rounds = fake_rounds()
        for r in rounds:
            r["trials"][0].pop("swap_guess", None)
        for r in rounds:
            for a in r["trials"][0]["agents"].values():
                a.pop("reflection", None)
        m = trial_metrics(rounds, "Q", 2)[0]
        self.assertIsNone(m["guess_score"])
        self.assertIsNone(m["time_to_detection"])
        self.assertEqual(m["guess_curve"], {})
        self.assertIsNone(m["trust_delta"])
        self.assertIsNotNone(m["coop_delta"])


class BootstrapTests(unittest.TestCase):
    def test_mean_and_interval_bracket_the_data(self):
        out = bootstrap_ci([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], n_boot=2000, seed=1)
        self.assertAlmostEqual(out["mean"], 5.5)
        self.assertLess(out["lo"], 5.5)
        self.assertGreater(out["hi"], 5.5)
        self.assertGreaterEqual(out["lo"], 1)
        self.assertLessEqual(out["hi"], 10)
        self.assertEqual(out["n"], 10)

    def test_same_seed_same_answer(self):
        v = [1.0, 4.0, 2.0, 8.0, 5.0, 7.0]
        self.assertEqual(bootstrap_ci(v, n_boot=500, seed=3), bootstrap_ci(v, n_boot=500, seed=3))

    def test_none_values_dropped_and_too_few_gives_none(self):
        self.assertEqual(bootstrap_ci([1, None, 3], n_boot=200, seed=0)["n"], 2)
        self.assertIsNone(bootstrap_ci([1.0], n_boot=200))
        self.assertIsNone(bootstrap_ci([None, None], n_boot=200))

    def test_constant_data_has_a_zero_width_interval(self):
        out = bootstrap_ci([2.0] * 6, n_boot=300, seed=0)
        self.assertEqual((out["lo"], out["hi"]), (2.0, 2.0))


class DiffTests(unittest.TestCase):
    def test_separated_groups_exclude_zero(self):
        a = [8, 9, 9, 10, 8, 9, 10, 9, 8, 9]
        b = [2, 3, 2, 1, 3, 2, 2, 3, 1, 2]
        out = diff_ci(a, b, n_boot=2000, seed=1)
        self.assertGreater(out["lo"], 0)
        self.assertAlmostEqual(out["diff"], sum(a) / 10 - sum(b) / 10)

    def test_identical_groups_include_zero(self):
        a = [3, 5, 4, 6, 5, 4, 3, 5, 6, 4]
        out = diff_ci(a, list(reversed(a)), n_boot=2000, seed=1)
        self.assertLessEqual(out["lo"], 0)
        self.assertGreaterEqual(out["hi"], 0)

    def test_too_few_gives_none(self):
        self.assertIsNone(diff_ci([1.0], [1.0, 2.0]))


class CurveTests(unittest.TestCase):
    def test_detection_share_is_cumulative_and_counts_never_detected(self):
        rows = [{"time_to_detection": t} for t in (1, 2, None, 2)]
        self.assertEqual(detection_share(rows, max_k=3), [0.25, 0.75, 0.75])
        self.assertEqual(detection_share([], max_k=2), [None, None])

    def test_curve_summary_gives_a_mean_and_interval_per_round(self):
        rows = [{"guess_curve": {3: 1.0 + i % 2, 4: 6.0 + i % 3}} for i in range(8)]
        out = curve_summary(rows, rounds=[3, 4], n_boot=300, seed=1)
        self.assertEqual(sorted(out), [3, 4])
        self.assertLess(out[3]["mean"], out[4]["mean"])
        self.assertLessEqual(out[4]["lo"], out[4]["mean"])
        self.assertGreaterEqual(out[4]["hi"], out[4]["mean"])

    def test_curve_summary_skips_rounds_with_too_little_data(self):
        out = curve_summary([{"guess_curve": {3: 2.0}}], rounds=[3], n_boot=100)
        self.assertIsNone(out[3])


class BinomialTests(unittest.TestCase):
    def test_exact_interval_matches_known_values(self):
        # Clopper-Pearson 95% for 0/10 is [0, 0.308]; for 10/10 it is [0.692, 1]; for 5/10 [0.187, 0.813]
        z = exact_binomial_ci(0, 10)
        self.assertEqual((z["lo"], round(z["hi"], 3)), (0.0, 0.308))
        o = exact_binomial_ci(10, 10)
        self.assertEqual((round(o["lo"], 3), o["hi"]), (0.692, 1.0))
        h = exact_binomial_ci(5, 10)
        self.assertEqual((round(h["lo"], 3), round(h["hi"], 3)), (0.187, 0.813))
        self.assertEqual(h["rate"], 0.5)

    def test_empty_gives_none(self):
        self.assertIsNone(exact_binomial_ci(0, 0))

    def test_detection_summary_counts_final_ever_and_placebo(self):
        rows = [
            {"guess_score": 9.0, "placebo_score": 1.5, "time_to_detection": 1},
            {"guess_score": 2.0, "placebo_score": 7.0, "time_to_detection": None},
            {"guess_score": 8.0, "placebo_score": 2.0, "time_to_detection": 2},
            {"guess_score": None, "placebo_score": None, "time_to_detection": None},   # no guess data
        ]
        out = detection_summary(rows)
        self.assertEqual((out["final"]["k"], out["final"]["n"]), (2, 3))
        self.assertEqual((out["ever"]["k"], out["ever"]["n"]), (2, 3))      # the trial without data is excluded
        self.assertEqual((out["placebo"]["k"], out["placebo"]["n"]), (1, 3))


class PaperMetricsTests(unittest.TestCase):
    def rounds(self):
        # 4 rounds, swap after round 2. Q: keeps promises pre, breaks post. J,M: keep promises always.
        out = []
        for r in range(4):
            post = r >= 2
            def ag(pd, cb, q_score=None):
                a = {"promise_deception": pd, "commitment_breaking": cb,
                     "stage2": {"stated_action": "CHEAP"}, "stage3": {"choice": "CHEAP"}}
                if q_score is not None:
                    a["reflection"] = {"takeaways": {"Q": {"score": q_score, "assessment": "x"}}}
                return a
            agents = {"J": ag(False, False, 5 if not post else 1), "M": ag(False, False, 5 if not post else 1),
                      "Q": ag(post, post)}      # Q deceives and breaks only after the swap
            out.append({"round_id": r, "trials": [{"trial_id": 0, "agents": agents}]})
        return out

    def test_rates_before_and_after_for_swapped_and_incumbents(self):
        m = paper_metrics(self.rounds(), "Q", 2)[0]
        self.assertEqual(m["swapped_cb_pre"], 0.0)
        self.assertEqual(m["swapped_cb_post"], 1.0)
        self.assertEqual(m["swapped_pd_post"], 1.0)
        self.assertEqual(m["incumbent_cb_pre"], 0.0)
        self.assertEqual(m["incumbent_cb_post"], 0.0)

    def test_trust_gap_is_kept_minus_broken(self):
        m = paper_metrics(self.rounds(), "Q", 2)[0]
        self.assertEqual(m["trust_gap"], 5.0 - 1.0)           # peers trusted Q at 5 when it kept, 1 when it broke

    def test_trust_gap_is_none_without_both_kinds_of_round(self):
        rounds = self.rounds()
        for r in rounds:
            r["trials"][0]["agents"]["Q"]["commitment_breaking"] = False
        self.assertIsNone(paper_metrics(rounds, "Q", 2)[0]["trust_gap"])


class InteractionTests(unittest.TestCase):
    def test_additive_effects_give_zero_interaction(self):
        b = [1, 1, 2, 1, 2, 1, 1, 2]
        c = [x + 8 for x in b]                      # behaviour adds 8
        d = [x + 1 for x in b]                      # identity adds 1
        e = [x + 9 for x in b]                      # both add 9
        out = interaction_ci(e, d, c, b, n_boot=1000, seed=1)
        self.assertAlmostEqual(out["interaction"], 0.0)
        self.assertLessEqual(out["lo"], 0)
        self.assertGreaterEqual(out["hi"], 0)

    def test_non_additive_effects_are_flagged(self):
        b = [1, 1, 2, 1, 2, 1, 1, 2]
        c = [1, 2, 1, 1, 2, 1, 2, 1]
        d = [1, 1, 2, 1, 1, 2, 1, 1]
        e = [9, 10, 9, 9, 10, 9, 9, 10]              # only both together are detected
        out = interaction_ci(e, d, c, b, n_boot=1000, seed=1)
        self.assertGreater(out["interaction"], 6)
        self.assertGreater(out["lo"], 0)

    def test_too_few_gives_none(self):
        self.assertIsNone(interaction_ci([1.0], [1.0, 2.0], [1.0, 2.0], [1.0, 2.0]))


class PermutationTests(unittest.TestCase):
    def test_separated_groups_give_small_p(self):
        a = [8, 9, 9, 10, 8, 9, 10, 9, 8, 9]
        b = [2, 3, 2, 1, 3, 2, 2, 3, 1, 2]
        self.assertLess(permutation_pvalue(a, b, n_perm=2000, seed=1), 0.01)

    def test_identical_groups_give_large_p(self):
        a = [3, 5, 4, 6, 5, 4, 3, 5, 6, 4]
        self.assertGreater(permutation_pvalue(a, list(reversed(a)), n_perm=2000, seed=1), 0.5)

    def test_p_is_never_zero(self):
        self.assertGreater(permutation_pvalue([10] * 5, [0] * 5, n_perm=200, seed=0), 0)

    def test_too_few_gives_none(self):
        self.assertIsNone(permutation_pvalue([1.0], [2.0, 3.0]))


if __name__ == "__main__":
    unittest.main()
