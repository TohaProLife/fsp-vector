import hashlib
import json
import math
import unittest
from copy import deepcopy
from unittest.mock import patch

from app.assessment_review import REVIEW_VERSION, review_submission
from app.engines.assessment import create_form, public_form, grade_form
from evaluation.reference_solvers import reference_answer


def snapshot():
    return {"blueprint_version": "stored-v1", "bank_version": "stored-bank",
            "rubric_version": "stored-rubric", "context": None,
            "items": [{"id": "choice", "type": "single_choice", "options": [
                {"id": "a", "label": "Вариант А"}, {"id": "b", "label": "Вариант Б"}]},
                {"id": "number", "type": "number"},
                {"id": "json", "type": "json"},
                {"id": "sql", "type": "sql"}]}


def answers():
    return {"choice": "a", "number": "1,5", "json": [], "sql": "SELECT 1"}


class AssessmentReviewTests(unittest.TestCase):
    def test_complete_public_values_and_no_oracle_execution_or_mutation(self):
        form = create_form("backend", "middle", seed=913)
        public = public_form(form)
        values = {item["id"]: reference_answer(item) for item in public["items"]}
        before = deepcopy((form, public, values))
        with patch("app.engines.assessment.grade_form", side_effect=AssertionError("grader called")), patch("app.engines.assessment.execute_select", side_effect=AssertionError("SQL called")):
            review = review_submission(public, {}, values)
        self.assertTrue(review["structural_ready"])
        self.assertEqual((review["answered"], review["total"]), (12, 12))
        self.assertEqual((form, public, values), before)
        self.assertEqual(set(review), {"answered", "total", "structural_ready", "issues", "public_form_sha256", "saved_answers_sha256", "prospective_answers_sha256", "review_token", "limitations"})
        self.assertNotIn("score", review)
        self.assertNotIn("passed", review)
        self.assertNotIn("confirmed_grade", review)

    def test_empty_json_containers_and_zero_are_answers_whitespace_is_missing(self):
        values = answers()
        for empty in ([], {}, "[]", "{}", '""'):
            values.update({"json": empty, "number": 0})
            review = review_submission(snapshot(), {}, values)
            self.assertTrue(review["structural_ready"])
            self.assertEqual(review["answered"], 4)
        for empty in (None, "", " \n\t"):
            values["json"] = empty
            review = review_submission(snapshot(), {}, values)
            self.assertFalse(review["structural_ready"])
            self.assertEqual(review["answered"], 3)
            self.assertEqual(review["issues"][0]["kind"], "missing")

    def test_formats_reject_foreign_choice_bool_nonfinite_and_malformed_json(self):
        cases = [("choice", "foreign"), ("choice", []), ("number", True),
                 ("number", "NaN"), ("number", "Infinity"),
                 ("json", "{broken"), ("json", '{"x":NaN}'),
                 ("json", '{"x":1,"x":2}'), ("json", {"x": math.inf}),
                 ("sql", {"query": False})]
        for item_id, value in cases:
            with self.subTest(item=item_id, value=value):
                values = {**answers(), item_id: value}
                review = review_submission(snapshot(), {}, values)
                self.assertFalse(review["structural_ready"])
                self.assertEqual(review["answered"], 4)
                self.assertTrue(any(row["item_id"] == item_id and row["kind"] == "format" for row in review["issues"]))

    def test_limits_utf8_depth_nodes_keys_and_oversized_body_are_bounded(self):
        deep = []
        for _ in range(22):
            deep = [deep]
        cases = [("sql", "я" * 6001), ("json", " " * 16001 + "[]"),
                 ("json", [0] * 1001), ("json", deep),
                 ("json", {"a" * 257: 1}), ("json", ["я" * 8001])]
        for item_id, value in cases:
            with self.subTest(item=item_id):
                review = review_submission(snapshot(), {}, {**answers(), item_id: value})
                self.assertFalse(review["structural_ready"])
                self.assertTrue(any(row["item_id"] == item_id and row["kind"] in ("limit", "format") for row in review["issues"]))
        cycle = []
        cycle.append(cycle)
        review = review_submission(snapshot(), {}, {**answers(), "json": cycle})
        self.assertIsNone(review["prospective_answers_sha256"])
        self.assertIsNone(review["review_token"])
        self.assertFalse(review["structural_ready"])
        review = review_submission(snapshot(), {}, {**answers(), "sql": "X" * 100001})
        self.assertIsNone(review["review_token"])

    def test_fingerprint_protects_final_values_form_and_survives_equivalent_autosave(self):
        form = snapshot()
        values = answers()
        first = review_submission(form, {}, values)
        saved = review_submission(form, values, {})
        reordered = review_submission(form, {}, dict(reversed(list(values.items()))))
        self.assertEqual(first["review_token"], saved["review_token"])
        self.assertEqual(first["review_token"], reordered["review_token"])
        self.assertNotEqual(first["saved_answers_sha256"], saved["saved_answers_sha256"])
        changed = review_submission(form, values, {"number": "1,6"})
        self.assertNotEqual(first["review_token"], changed["review_token"])
        changed_form = deepcopy(form)
        changed_form["items"][2]["prompt"] = "Обновлённое условие"
        self.assertNotEqual(first["review_token"], review_submission(changed_form, {}, values)["review_token"])
        canonical = json.dumps({"review_version": REVIEW_VERSION,
                                "public_form_sha256": first["public_form_sha256"],
                                "prospective_answers_sha256": first["prospective_answers_sha256"]},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertEqual(first["review_token"], hashlib.sha256(canonical).hexdigest())
        # Consistency is not CAS over earlier saved versions or authorization.
        self.assertEqual(first["review_token"], review_submission(form, {"number": "9"}, values)["review_token"])

    def test_unknown_ids_no_answer_echo_private_keys_ignored_and_bad_inputs_fail_closed(self):
        form = snapshot()
        first = review_submission(form, {}, answers())
        form["private_payload"] = {"secret": "SECRET_ORACLE"}
        form["items"][0]["_oracle"] = {"expected": "SECRET_ORACLE"}
        self.assertEqual(first["review_token"], review_submission(form, {}, answers())["review_token"])
        review = review_submission(form, {}, {**answers(), "SECRET_KEY": "SECRET_VALUE"})
        self.assertFalse(review["structural_ready"])
        self.assertTrue(any(row["item_id"] is None and row["kind"] == "format" for row in review["issues"]))
        serialized = json.dumps(review, ensure_ascii=False)
        for secret in ("SECRET_ORACLE", "SECRET_KEY", "SECRET_VALUE"):
            self.assertNotIn(secret, serialized)
        for saved, draft in (([], {}), ({}, []), ({}, {"number": object()})):
            review = review_submission(snapshot(), saved, draft)
            self.assertFalse(review["structural_ready"])
            self.assertIsNone(review["review_token"])
        duplicate = snapshot()
        duplicate["items"][1]["id"] = "choice"
        with self.assertRaises(ValueError):
            review_submission(duplicate, {}, {})

    def test_repair_overwrites_invalid_saved_value_and_readiness_never_means_pass(self):
        saved = {**answers(), "json": math.nan}
        review = review_submission(snapshot(), saved, {"json": []})
        self.assertTrue(review["structural_ready"])
        self.assertIsNone(review["saved_answers_sha256"])
        self.assertIsNotNone(review["review_token"])
        form = create_form("backend", "intern", seed=42)
        public = public_form(form)
        values = {}
        for item in public["items"]:
            values[item["id"]] = item["options"][0]["id"] if item["type"] == "single_choice" else 999999 if item["type"] == "number" else "SELECT 999999" if item["type"] == "sql" else {}
        self.assertTrue(review_submission(public, {}, values)["structural_ready"])
        self.assertFalse(grade_form(form, values)["passed"])


if __name__ == "__main__":
    unittest.main()
