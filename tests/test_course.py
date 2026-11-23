import unittest

import course


class CourseLabTests(unittest.TestCase):
    def test_night_bus_and_trace(self):
        result = course.capture()
        self.assertEqual(result["arrival"], "2026-04-13T06:40:00")
        self.assertIn(["取消", "重訂", 1], result["directly_follows"])

    def test_review_budget(self):
        result = course.review()
        self.assertEqual(result["disagreement"]["reviewed"], ["M3", "M4"])
        self.assertEqual(result["disagreement"]["errors_found"], 2)

    def test_arrival_deadline(self):
        self.assertEqual(course.impact(25)["hotel"]["status"], "within_limit")
        self.assertEqual(course.impact(26)["hotel"]["status"], "recheck")
        self.assertEqual(course.impact()["locker"]["status"], "unknown")

    def test_retrieval_and_fusion(self):
        unfiltered = course.retrieval(k=2)
        self.assertFalse(unfiltered[0]["complete"])
        self.assertTrue(unfiltered[1]["obsolete_hit"])
        filtered = course.retrieval(k=3, filter_obsolete=True)
        self.assertTrue(all(row["complete"] for row in filtered))
        self.assertFalse(any(row["obsolete_hit"] for row in filtered))
        self.assertEqual(course.rrf([["X", "Y"], ["Y", "Z"]])[0], "Y")

    def test_evaluation(self):
        result = course.evaluate()
        self.assertTrue(all(row["complete"] for row in result["oracle"]))
        self.assertEqual(result["toy_evidence_curve"][0]["coverage"], 1)
        self.assertEqual(result["toy_evidence_curve"][0]["risk"], 0.5)

    def test_capstone_and_idempotency(self):
        result = course.capstone()
        self.assertEqual(result["hotel"]["decision"], "keep")
        self.assertEqual(result["ticket"]["decision"], "traveler_B_misses_start")
        self.assertEqual(result["simulated_writes"], 1)
        self.assertEqual(course.capstone(other_guests=0)["hotel"]["decision"], "review_checkin")
        self.assertEqual(result["dry_run"], ["needs_approval", "applied", "already_applied"])
        booking = course.SimulatedBooking()
        self.assertEqual(booking.change_dinner(1, True, "id"), "applied")
        self.assertEqual(booking.change_dinner(2, True, "id"), "key_conflict")
