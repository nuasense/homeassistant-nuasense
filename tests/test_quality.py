"""The data quality sensor's state and attributes, from the API's quality block.

    python3 -m unittest discover -s tests -p test_quality.py
    (the whole suite: pytest tests -o asyncio_mode=auto, with requirements_test.txt)
"""

import importlib.util
import pathlib
import unittest

SPEC = importlib.util.spec_from_file_location(
    "quality", pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "nuasense" / "quality.py"
)
quality = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quality)

BLOCK = {
    "grade": "D",
    "graded_at": "2026-11-13T04:00:00Z",
    "references": [{"kind": "model", "name": "NASA POWER hourly"}, {"kind": "official_station", "name": "METAR HKNV Naivasha", "distance_km": 14.2}],
    "sensors": {
        "rain": {"grade": "D", "issues": [{"severity": "fault", "text": "4.3 mm against 75.6 mm in the area", "fix": "Check the funnel for leaves, nests or dirt, and that the tipping bucket moves."}]},
        "temperature": {"grade": "A", "issues": []},
        "wind": {"grade": None, "issues": [{"severity": "note", "text": "wind always 0 (no anemometer?)"}]},
    },
    "now": {"fields": {"temperature": {"status": "ok"}, "wind_speed": {"status": "stuck", "reason": "the same value (0.4) for 3.5 h"}}},
}


class QualityTest(unittest.TestCase):
    def test_state_is_the_grade(self):
        self.assertEqual(quality.quality_state(BLOCK), "D")
        self.assertEqual(quality.quality_state({"grade": None, "not_graded": "fewer than 72 hours"}), "not_graded")
        self.assertIsNone(quality.quality_state(None))

    def test_attributes_say_what_to_fix(self):
        a = quality.quality_attributes(BLOCK)
        self.assertEqual(len(a["problems"]), 1)
        self.assertTrue(a["problems"][0].startswith("Rain gauge (D): 4.3 mm against 75.6 mm"))
        self.assertIn("funnel", a["problems"][0])
        self.assertEqual(a["wrong_right_now"], ["Wind: the same value (0.4) for 3.5 h"])
        self.assertEqual(a["checked_against"], ["NASA POWER hourly", "METAR HKNV Naivasha (14.2 km)"])
        self.assertEqual(a["grade_rain"], "D")
        self.assertEqual(a["grade_temperature"], "A")
        self.assertNotIn("grade_wind", a)
        self.assertNotIn("anemometer", str(a), "notes stay out")

    def test_block_found_in_listing_or_first_look(self):
        self.assertEqual(quality.quality_of({"station": {"quality": BLOCK}})["grade"], "D")
        self.assertEqual(quality.quality_of({"station": {}, "first_look": {"quality": BLOCK}})["grade"], "D")
        self.assertIsNone(quality.quality_of({"station": {}, "first_look": {}}))


if __name__ == "__main__":
    unittest.main()
