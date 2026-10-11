"""Release regressions for provenance validity and malformed submitted text."""

import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from app.engines.assessment import create_form, grade_form, public_form
from app.engines.matching import ALGORITHM_VERSION, admission, evidence_map, freshness_signal, fsp_signal, rank_candidates
from app.engines.safe_sql import execute_select
from evaluation.reference_solvers import reference_answer

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


class FinalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.need = {"specialization": "backend", "grade": "middle", "required_skills": ["SQL"], "skills": ["API"]}
        self.candidate = {"id": "candidate", "specialization": "backend", "confirmed_grade": "middle", "published": True,
                          "score": 90, "assessment_at": (NOW - timedelta(days=365)).isoformat(),
                          "evidence": [{"skill": "SQL", "source": "ASSESSMENT_VERIFIED", "status": "verified", "score": 90,
                                        "scope": {"specialization": "backend", "grade": "middle"}}]}
        self.achievement = {"event_id": "event-1", "title": "Synthetic registry event", "discipline": "Algorithms",
                            "date": NOW.isoformat(), "place": 1, "participants": 100, "status": "active"}
        self.candidate["fsp"] = {"status": "sync_ok", "source": "FSP_DEMO_CONFIRMED", "achievements": [self.achievement]}

    def test_unknown_status_cannot_satisfy_a_formal_requirement(self):
        for status in ("pending", "cancelled", "observed", "verified_later", "", None, True, " revoked "):
            with self.subTest(status=status):
                candidate = deepcopy(self.candidate)
                candidate["evidence"][0]["status"] = status
                self.assertEqual(evidence_map(candidate, "backend"), {})
                self.assertIn("required_evidence_missing", admission(self.need, candidate)["reasons"])
                self.assertEqual(rank_candidates(self.need, [candidate], NOW), [])
        for status in ("active", " VERIFIED "):
            self.candidate["evidence"][0]["status"] = status
            self.assertTrue(admission(self.need, self.candidate)["eligible"])

    def test_unknown_practice_status_has_no_freshness_or_coverage(self):
        practice = {"skill": "API", "source": "PRACTICE_OBSERVED", "score": 100, "objectively_graded": True,
                    "confirmed_at": NOW.isoformat(), "scope": {"specialization": "backend"}}
        base = rank_candidates(self.need, [self.candidate], NOW)[0]
        for status in ("pending", "expired", "", None, " revoked "):
            with self.subTest(status=status):
                candidate = deepcopy(self.candidate)
                candidate["evidence"].append({**practice, "status": status})
                self.assertEqual(freshness_signal(self.need, candidate, NOW)["practice_bonus"], 0)
                self.assertEqual(rank_candidates(self.need, [candidate], NOW)[0]["score"], base["score"])
        for status in (" active ", "observed", " OBSERVED "):
            candidate["evidence"][-1]["status"] = status
            self.assertEqual(freshness_signal(self.need, candidate, NOW)["practice_bonus"], .25)

    def test_demo_or_company_practice_cannot_be_mislabeled_as_formal_proof(self):
        for changes in ({"is_demo": True}, {"scope": {"specialization": "backend", "global_grade": False}}):
            candidate = deepcopy(self.candidate)
            candidate["evidence"][0].update(changes)
            self.assertFalse(admission(self.need, candidate)["eligible"])

    def test_fixture_explanations_and_later_formal_proof_use_per_record_provenance(self):
        candidate = deepcopy(self.candidate)
        candidate["source"] = "synthetic_fixture"
        candidate["evidence"][0].update(origin="SYNTHETIC_SEED", is_demo=True)
        fixture = rank_candidates(self.need, [candidate], NOW)[0]
        self.assertEqual(fixture["reasons"][0]["source_kind"], "synthetic_fixture")
        self.assertIn("Синтетические", next(row["text"] for row in fixture["reasons"] if row["kind"] == "evidence"))
        candidate["evidence"] = deepcopy(self.candidate["evidence"])
        formal = rank_candidates(self.need, [candidate], NOW)[0]
        self.assertEqual(formal["reasons"][0]["source_kind"], "formal_assessment")
        self.assertIn("Проверены экзаменом", next(row["text"] for row in formal["reasons"] if row["kind"] == "evidence"))

    def test_registry_revocation_dominates_active_duplicate_in_every_order(self):
        active = deepcopy(self.achievement)
        for changes in ({"revoked": True}, {"status": "revoked"}, {"status": " revoked "}, {"status": "unverified"}):
            revoked = {**active, **changes}
            for records in ([active, revoked], [revoked, active]):
                with self.subTest(changes=changes, records=records):
                    candidate = deepcopy(self.candidate)
                    candidate["fsp"]["achievements"] = records
                    self.assertEqual(fsp_signal(candidate, "backend", NOW), (0, []))
                    row = rank_candidates(self.need, [candidate], NOW)[0]
                    self.assertEqual(row["breakdown"]["fsp"]["points"], 0)
                    self.assertFalse(any(reason["kind"] == "fsp" for reason in row["reasons"]))

    def test_only_well_formed_current_registry_records_contribute(self):
        invalid = [{"status": "pending"}, {"source": "SELF_DECLARED"}, {"date": None}, {"date": "invalid"},
                   {"date": (NOW + timedelta(seconds=1)).isoformat()}, {"place": True}, {"place": 1.5},
                   {"participants": True}, {"participants": float("inf")}, {"participants": 1.5},
                   {"participants": 0}, {"place": 101}, {"event_id": ["invalid"]}]
        for changes in invalid:
            with self.subTest(changes=changes):
                candidate = deepcopy(self.candidate)
                candidate["fsp"]["achievements"][0].update(changes)
                self.assertEqual(fsp_signal(candidate, "backend", NOW), (0, []))
        malformed = deepcopy(self.candidate)
        malformed["fsp"]["achievements"] = [None, "invalid", deepcopy(self.achievement)]
        self.assertGreater(fsp_signal(malformed, "backend", NOW)[0], 0)

    def test_duplicates_cannot_inflate_signal_or_mask_demo_provenance(self):
        baseline = fsp_signal(self.candidate, "backend", NOW)
        self.candidate["fsp"]["achievements"] *= 20
        self.assertEqual(fsp_signal(self.candidate, "backend", NOW), baseline)
        self.candidate["fsp"]["source"] = "FSP_REGISTRY_VERIFIED"
        self.candidate["fsp"]["is_demo"] = True
        row = rank_candidates(self.need, [self.candidate], NOW)[0]
        self.assertIn("Демонстрационный", next(reason["text"] for reason in row["reasons"] if reason["kind"] == "fsp"))
        self.assertLessEqual(row["breakdown"]["fsp"]["points"], 5)

    def test_new_version_fits_persisted_algorithm_identifier(self):
        self.assertLessEqual(len(ALGORITHM_VERSION), 80)
        self.assertLessEqual(len(ALGORITHM_VERSION.replace("semantic-neutral", "cpu-tfidf")), 80)

    def test_malformed_unicode_is_rejected_without_crashing_the_other_answers(self):
        dataset = {"sample": {"columns": {"value": "INTEGER"}, "rows": [[1]]}}
        self.assertFalse(execute_select("SELECT '\ud800' FROM sample", dataset)["ok"])
        self.assertTrue(execute_select("SELECT value FROM sample", dataset)["ok"])
        form = create_form("backend", "middle", seed=991)
        answers = {item["id"]: reference_answer(item) for item in public_form(form)["items"]}
        json_item = next(item for item in form["items"] if item["type"] == "json")
        for invalid in ('"\ud800"', '{"value":"\\ud800"}', {"value": "\ud800"}, {"\ud800": 1}):
            changed = deepcopy(answers)
            changed[json_item["id"]] = invalid
            result = grade_form(form, changed)
            feedback = next(row for row in result["feedback"] if row["item_id"] == json_item["id"])
            self.assertEqual(feedback["earned_score"], 0)
            self.assertGreater(result["score"], 80)


if __name__ == "__main__":
    unittest.main()
