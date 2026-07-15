import threading
import time
import types
import unittest
from unittest import mock

from canbusd import dispatcher


class DispatcherTests(unittest.TestCase):
    def test_event_is_published_even_without_binding(self):
        with (
            mock.patch.object(dispatcher, "publish") as publish,
            self.assertLogs("canbusd.dispatcher", level="WARNING") as logs,
        ):
            dispatcher.dispatch("button:pressed", None, [7])

        publish.assert_called_once_with("button:pressed", [7])
        self.assertIn("No binding configured", "\n".join(logs.output))

    def test_action_receives_configured_and_dynamic_arguments(self):
        action_fn = mock.Mock()
        module = types.SimpleNamespace(run=action_fn)
        real_import = __import__

        def import_module(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "actions.demo":
                return module
            return real_import(name, globals, locals, fromlist, level)

        with (
            mock.patch.object(dispatcher, "publish") as publish,
            mock.patch("builtins.__import__", side_effect=import_module),
        ):
            dispatcher.dispatch(
                "demo:event",
                {"module": "demo", "func": "run", "args": ["fixed"]},
                [4, 5],
            )

        publish.assert_called_once_with("demo:event", [4, 5])
        action_fn.assert_called_once_with("fixed", 4, 5)

    def test_invalid_binding_is_logged_without_importing(self):
        with (
            mock.patch.object(dispatcher, "publish"),
            self.assertLogs("canbusd.dispatcher", level="ERROR") as logs,
        ):
            with mock.patch("builtins.__import__") as importer:
                dispatcher.dispatch("bad:event", {"module": "audio"})

        action_imports = [
            call for call in importer.call_args_list
            if call.args and str(call.args[0]).startswith("actions.")
        ]
        self.assertEqual(action_imports, [])
        self.assertIn("Invalid binding", "\n".join(logs.output))

    def test_action_exception_is_isolated(self):
        module = types.SimpleNamespace(run=mock.Mock(side_effect=RuntimeError("boom")))
        real_import = __import__

        def import_module(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "actions.demo":
                return module
            return real_import(name, globals, locals, fromlist, level)

        with (
            mock.patch.object(dispatcher, "publish"),
            mock.patch("builtins.__import__", side_effect=import_module),
            self.assertLogs("canbusd.dispatcher", level="ERROR") as logs,
        ):
            dispatcher.dispatch("demo:event", {"module": "demo", "func": "run"})

        self.assertIn("Action failed", "\n".join(logs.output))


class ActionQueueTests(unittest.TestCase):
    def test_slow_action_does_not_block_event_publication_or_submission(self):
        started = threading.Event()
        release = threading.Event()
        executed = []

        def slow_action(event, action, extra_args):
            executed.append((event, extra_args))
            started.set()
            release.wait(1.0)

        with (
            mock.patch.object(dispatcher, "publish") as publish,
            mock.patch.object(dispatcher, "_execute_action", side_effect=slow_action),
        ):
            worker = dispatcher.ActionQueue(maxsize=4)
            began = time.monotonic()
            self.assertTrue(worker.dispatch("media:pause", {"module": "audio", "func": "play_pause"}))
            elapsed = time.monotonic() - began
            self.assertLess(elapsed, 0.1)
            self.assertTrue(started.wait(0.5))
            self.assertTrue(worker.dispatch("media:next", {"module": "audio", "func": "next_track"}))
            publish.assert_has_calls([
                mock.call("media:pause", None),
                mock.call("media:next", None),
            ])
            release.set()
            worker.close(timeout=1.0)

        self.assertEqual(
            executed,
            [("media:pause", None), ("media:next", None)],
        )

    def test_bounded_queue_logs_and_drops_newest_action_on_overload(self):
        started = threading.Event()
        release = threading.Event()

        def blocked_action(_event, _action, _extra_args):
            started.set()
            release.wait(1.0)

        with (
            mock.patch.object(dispatcher, "publish"),
            mock.patch.object(dispatcher, "_execute_action", side_effect=blocked_action),
            self.assertLogs("canbusd.dispatcher", level="ERROR") as logs,
        ):
            worker = dispatcher.ActionQueue(maxsize=1)
            self.assertTrue(worker.dispatch("first", {"module": "audio", "func": "play_pause"}))
            self.assertTrue(started.wait(0.5))
            self.assertTrue(worker.dispatch("second", {"module": "audio", "func": "next_track"}))
            self.assertFalse(worker.dispatch("third", {"module": "audio", "func": "prev_track"}))
            release.set()
            worker.close(timeout=1.0)

        self.assertIn("Action queue full", "\n".join(logs.output))

    def test_queue_rejects_invalid_or_missing_bindings_without_worker_work(self):
        with (
            mock.patch.object(dispatcher, "publish") as publish,
            mock.patch.object(dispatcher, "_execute_action") as execute,
        ):
            worker = dispatcher.ActionQueue(maxsize=2)
            self.assertFalse(worker.dispatch("missing", None))
            self.assertFalse(worker.dispatch("invalid", {"module": "audio"}))
            worker.close(timeout=1.0)

        self.assertEqual(publish.call_count, 2)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
