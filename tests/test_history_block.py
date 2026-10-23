import unittest

from src.endogenous.core.history import build_history_block, make_round_record

OUTCOMES = {"choices": {"M": "CHEAP", "Q": "CHEAP"}, "payoffs": {"M": 3.0, "Q": 3.0}}


def record(round_idx=0, m_msg="M: let us both go CHEAP", q_msg="Q: agreed, CHEAP"):
    return make_round_record(
        round_idx,
        plans={"M": "CHEAP", "Q": "EXPENSIVE"},
        announcements={
            "M": {"stated_action": "CHEAP", "message": m_msg, "extra": "dropped"},
            "Q": {"stated_action": "CHEAP", "message": q_msg},
        },
        outcomes=OUTCOMES,
    )


class HistoryBlockTests(unittest.TestCase):
    def test_empty_history_renders_nothing(self):
        self.assertEqual(build_history_block("M", []), "")

    def test_messages_are_verbatim_and_rounds_in_order(self):
        block = build_history_block("M", [record(0, m_msg="first-msg"), record(1, m_msg="second-msg")])
        self.assertIn('Agent M (you) announced CHEAP: "first-msg"', block)
        self.assertIn('Agent Q announced CHEAP: "Q: agreed, CHEAP"', block)
        self.assertLess(block.index("Round 1:"), block.index("Round 2:"))
        self.assertLess(block.index("first-msg"), block.index("second-msg"))

    def test_choices_and_payoffs_are_shown(self):
        block = build_history_block("M", [record()])
        self.assertIn("Agent M chose CHEAP and earned 3.0", block)
        self.assertIn("Agent Q chose CHEAP and earned 3.0", block)

    def test_agent_sees_only_its_own_plan(self):
        # Q privately planned EXPENSIVE and then chose CHEAP, so the word EXPENSIVE
        # appears in the record only as Q's private plan.
        m_block = build_history_block("M", [record()])
        q_block = build_history_block("Q", [record()])
        self.assertIn("Your private plan: CHEAP", m_block)
        self.assertNotIn("EXPENSIVE", m_block)
        self.assertIn("Your private plan: EXPENSIVE", q_block)

    def test_record_stores_no_reasoning(self):
        rec = record()
        self.assertEqual(set(rec), {"round_id", "plans", "announcements", "choices", "payoffs"})
        self.assertEqual(set(rec["announcements"]["M"]), {"stated_action", "message"})

    def test_missing_values_render_safely(self):
        rec = make_round_record(0, {"M": None, "Q": None},
                                {"M": {"stated_action": None, "message": ""}, "Q": {}},
                                {"choices": {"M": None, "Q": "CHEAP"}, "payoffs": {"M": None, "Q": 2.0}})
        block = build_history_block("M", [rec])
        self.assertIn("Your private plan: unknown", block)
        self.assertIn("Agent M chose unknown and earned n/a", block)


if __name__ == "__main__":
    unittest.main()
