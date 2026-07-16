import unittest
from unittest import mock

from canbusd import event_bus
from canbusd.event_bus import EventBus


class EventBusTests(unittest.TestCase):
    def test_publish_delivers_payload_and_returns_success_count(self):
        bus = EventBus()
        received = []
        bus.subscribe("vehicle:ready", received.append)

        delivered = bus.publish("vehicle:ready", {"present": True})

        self.assertEqual(delivered, 1)
        self.assertEqual(received, [{"present": True}])

    def test_failing_subscriber_is_isolated_from_following_subscribers(self):
        bus = EventBus()
        received = []

        def broken(_payload):
            raise RuntimeError("subscriber exploded")

        bus.subscribe("demo", broken)
        bus.subscribe("demo", received.append)

        with self.assertLogs("canbusd.event_bus", level="ERROR") as logs:
            delivered = bus.publish("demo", 42)

        self.assertEqual(delivered, 1)
        self.assertEqual(received, [42])
        self.assertIn("Subscriber failed for event=demo", "\n".join(logs.output))

    def test_unsubscribe_and_clear_are_explicit(self):
        bus = EventBus()
        first = []
        second = []
        bus.subscribe("one", first.append)
        bus.subscribe("two", second.append)

        self.assertTrue(bus.unsubscribe("one", first.append))
        self.assertFalse(bus.unsubscribe("one", first.append))
        bus.publish("one", 1)
        bus.publish("two", 2)
        self.assertEqual(first, [])
        self.assertEqual(second, [2])

        bus.clear()
        bus.publish("two", 3)
        self.assertEqual(second, [2])

    def test_missing_callback_and_event_specific_clear_are_safe(self):
        bus = EventBus()
        received = []
        bus.subscribe("one", received.append)

        self.assertFalse(bus.unsubscribe("one", lambda _payload: None))
        bus.clear("one")
        self.assertEqual(bus.publish("one", 1), 0)

    def test_module_level_api_delegates_to_default_bus(self):
        replacement = EventBus()
        received = []
        with mock.patch.object(event_bus, "_default_bus", replacement):
            event_bus.subscribe("module", received.append)
            self.assertEqual(event_bus.publish("module", "payload"), 1)
            self.assertTrue(event_bus.unsubscribe("module", received.append))
            event_bus.clear()

        self.assertEqual(received, ["payload"])

    def test_subscriber_changes_apply_to_the_next_publication(self):
        bus = EventBus()
        calls = []

        def late(payload):
            calls.append(("late", payload))

        def first(payload):
            calls.append(("first", payload))
            bus.subscribe("event", late)

        bus.subscribe("event", first)
        bus.publish("event", 1)
        bus.publish("event", 2)

        self.assertEqual(
            calls,
            [
                ("first", 1),
                ("first", 2),
                ("late", 2),
            ],
        )


if __name__ == "__main__":
    unittest.main()
