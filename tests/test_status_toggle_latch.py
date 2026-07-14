import unittest

from canbusd.status_rules import StatusRuleState, evaluate_status_rules, parse_status_rules


class StatusToggleLatchTests(unittest.TestCase):
    @staticmethod
    def _rule(**overrides):
        rule = {
            "id": "0x3E1",
            "byte": 0,
            "type": "bool",
            "path": "climate.rear_window_heater_requested",
            "mask": "0x04",
            "true": "0x04",
            "false": "0x00",
            "state": "toggle_latch",
            "initial": False,
        }
        rule.update(overrides)
        return parse_status_rules([rule])[int(rule["id"], 16)][0]

    @staticmethod
    def _value(rule, raw, state):
        update = evaluate_status_rules([rule], bytes([raw]), 1, state=state)
        return update["climate"]["rear_window_heater_requested"]

    def test_rising_edges_toggle_and_held_frames_do_not_repeat(self):
        rule = self._rule()
        state = StatusRuleState()

        self.assertFalse(self._value(rule, 0x00, state))
        self.assertTrue(self._value(rule, 0x04, state))
        self.assertTrue(self._value(rule, 0x04, state))
        self.assertTrue(self._value(rule, 0x00, state))
        self.assertFalse(self._value(rule, 0x04, state))

    def test_initial_true_is_respected_until_first_rising_edge(self):
        rule = self._rule(initial=True)
        state = StatusRuleState()

        self.assertTrue(self._value(rule, 0x00, state))
        self.assertFalse(self._value(rule, 0x04, state))

    def test_reset_restarts_the_lifecycle_from_configured_initial_state(self):
        rule = self._rule()
        state = StatusRuleState()

        self.assertTrue(self._value(rule, 0x04, state))
        self.assertTrue(self._value(rule, 0x00, state))

        state.reset()

        self.assertFalse(self._value(rule, 0x00, state))
        self.assertTrue(self._value(rule, 0x04, state))

    def test_decoder_instances_do_not_share_latch_state(self):
        rule = self._rule()
        first = StatusRuleState()
        second = StatusRuleState()

        self.assertTrue(self._value(rule, 0x04, first))
        self.assertFalse(self._value(rule, 0x00, second))

    def test_same_output_path_on_different_can_signals_does_not_collide(self):
        first_rule = self._rule(id="0x3E1")
        second_rule = self._rule(id="0x3E2")
        state = StatusRuleState()

        self.assertTrue(self._value(first_rule, 0x04, state))
        self.assertFalse(self._value(second_rule, 0x00, state))

    def test_explicit_state_key_can_intentionally_share_a_latch(self):
        first_rule = self._rule(id="0x3E1", state_key="rear-heater")
        second_rule = self._rule(id="0x3E2", state_key="rear-heater")
        state = StatusRuleState()

        self.assertTrue(self._value(first_rule, 0x04, state))
        self.assertTrue(self._value(second_rule, 0x00, state))


if __name__ == "__main__":
    unittest.main()
