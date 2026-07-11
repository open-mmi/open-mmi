import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
DOCS = ROOT / "ui" / "web_dashboard" / "README.md"


class RadioPrivacyConsentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP.read_text(encoding="utf-8")
        cls.docs = DOCS.read_text(encoding="utf-8")

    def test_consent_gate_loads_before_radio_adapter(self):
        consent = self.app.index("Open MMI Internet Radio privacy consent start")
        adapter = self.app.index("Open MMI media source adapters/radio start")
        self.assertLess(consent, adapter)

    def test_radio_enable_is_intercepted_in_capture_phase(self):
        self.assertIn('document.addEventListener("click", interceptRadioEnable, true)', self.app)
        self.assertIn("event.stopImmediatePropagation()", self.app)
        self.assertIn('data-openmmi-media-source-enable="radio"', self.app)

    def test_consent_is_versioned_and_fail_closed(self):
        self.assertIn('const CONSENT_KEY = "openmmi.media.radio.privacy-consent.v1"', self.app)
        self.assertIn('const NOTICE_VERSION = "2026-07-11-v1"', self.app)
        self.assertIn("!hasCurrentConsent() && disableRadioPreference()", self.app)
        self.assertIn("if (!saveConsent() || !hasCurrentConsent())", self.app)
        self.assertIn("sourceId !== \"radio\" || hasCurrentConsent()", self.app)

    def test_notice_names_material_external_disclosures(self):
        for phrase in [
            "public IP address",
            "search text and country/language filters",
            "station-click notification",
            "connection duration and data transferred",
            "does not request GPS location",
            "local storage",
        ]:
            self.assertIn(phrase, self.app)

    def test_docs_do_not_overpromise_external_privacy(self):
        self.assertIn("does not control the privacy", self.docs)
        self.assertIn("retention", self.docs)
        self.assertIn("openmmi.media.radio.privacy-consent.v1", self.docs)


if __name__ == "__main__":
    unittest.main()
