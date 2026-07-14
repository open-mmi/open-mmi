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


if __name__ == "__main__":
    unittest.main()
