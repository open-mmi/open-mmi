from __future__ import annotations

import unittest

from dashboard_contract_helpers import (
    css_properties,
    implemented_source_ids,
    javascript_function_body,
    js_bool_property,
    js_object_with_id,
    js_string_property,
)


class DashboardContractHelperTests(unittest.TestCase):
    def test_javascript_object_properties_ignore_spacing(self):
        source = '{\n id : "usb", label:"USB", planned : false\n}'
        obj = js_object_with_id(source, "usb")
        self.assertEqual(js_string_property(obj, "label"), "USB")
        self.assertFalse(js_bool_property(obj, "planned"))

    def test_implemented_sources_are_membership_based(self):
        source = 'return ["jellyfin", "radio", "usb", "bluetooth", "future"].includes(active);'
        self.assertEqual(
            implemented_source_ids(source),
            {"jellyfin", "radio", "usb", "bluetooth", "future"},
        )

    def test_function_body_handles_nested_blocks_and_strings(self):
        source = 'function demo() { if (ok) { return "}"; } return true; }'
        body = javascript_function_body(source, "demo")
        self.assertIn('return "}"', body)
        self.assertIn("return true", body)

    def test_css_properties_ignore_formatting(self):
        source = '.button,\n.other { border-color : #fff !important; opacity: 1; }'
        props = css_properties(source, ".button")
        self.assertEqual(props["border-color"], "#fff !important")
        self.assertEqual(props["opacity"], "1")


if __name__ == "__main__":
    unittest.main()
