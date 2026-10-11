import json
import unittest
from datetime import datetime,timedelta,timezone
from app.engines.assessment import create_form,public_form,grade_form,grade_challenge,cooldown_policy,catalog
from app.engines.taxonomy import SPECIALIZATIONS,GRADES
from app.engines.safe_sql import execute_select
from evaluation.reference_solvers import reference_answer,independent_sql_rows


class AssessmentTests(unittest.TestCase):
    def test_every_track_grade_has_complete_blueprint_and_independent_solver(self):
        for spec in SPECIALIZATIONS:
            for grade in GRADES:
                for seed in range(8):
                    with self.subTest(spec=spec,grade=grade,seed=seed):
                        private=create_form(spec,grade,seed=seed)
                        public=public_form(private)
                        self.assertEqual(len(public["items"]),12)
                        self.assertEqual(len({row["id"] for row in public["items"]}),12)
                        counts={comp:0 for comp in SPECIALIZATIONS[spec]["competencies"]}
                        for item in public["items"]:
                            counts[item["competency"]]+=1
                        self.assertEqual(set(counts.values()),{3})
                        answers={item["id"]:reference_answer(item) for item in public["items"]}
                        result=grade_form(private,answers)
                        self.assertEqual(result["score"],100)
                        self.assertTrue(result["passed"])
                        for item in public["items"]:
                            if item["type"]=="sql":
                                private_item=next(row for row in private["items"] if row["id"]==item["id"])
                                self.assertCountEqual(private_item["_oracle"]["rows"],independent_sql_rows(item))

    def test_public_projection_allowlist_drops_nested_answers_and_future_private_keys(self):
        private=create_form("backend","middle",seed=88)
        private["future_secret"]="DO_NOT_LEAK"
        private["items"][0]["sensitive"]={"password":"DO_NOT_LEAK"}
        public=public_form(private)
        serialized=json.dumps(public)
        self.assertNotIn("_oracle",serialized)
        self.assertNotIn("DO_NOT_LEAK",serialized)
        self.assertNotIn('"seed"',serialized)
        self.assertNotIn("family_id",serialized)
        public["items"][0]["prompt"]="changed by client"
        self.assertNotEqual(private["items"][0]["prompt"],public["items"][0]["prompt"])

    def test_zero_and_unknown_answers_do_not_pass(self):
        form=create_form("data","senior",seed=17)
        self.assertEqual(grade_form(form,{})["score"],0)
        self.assertFalse(grade_form(form,{})["passed"])
        with self.assertRaises(ValueError): grade_form(form,{"foreign-item":"answer"})

    def test_total_does_not_override_competency_or_practice_minimum(self):
        form=create_form("backend","middle",seed=91)
        items=public_form(form)["items"]
        answers={item["id"]:reference_answer(item) for item in items}
        weak=items[0]["competency"]
        for item in items:
            if item["competency"]==weak: answers.pop(item["id"])
        result=grade_form(form,answers)
        self.assertEqual(result["score"],75)
        self.assertFalse(result["passed"])
        answers={item["id"]:reference_answer(item) for item in items if item["slot"] not in ("practice","mutation")}
        result=grade_form(form,answers)
        self.assertEqual(result["practice_score"],0)
        self.assertFalse(result["passed"])

    def test_numeric_true_nan_and_infinite_not_correct(self):
        form=create_form("data","intern",seed=91)
        numeric=next(row for row in form["items"] if row["type"]=="number")
        for value in (True,"NaN","Infinity",False,{"value":True}):
            feedback=grade_form(form,{numeric["id"]:value})["feedback"]
            row=next(row for row in feedback if row["item_id"]==numeric["id"])
            self.assertEqual(row["earned_score"],0)

    def test_repeatable_form_and_new_seed_changes_data(self):
        a=create_form("backend","middle",seed=111)
        b=create_form("backend","middle",seed=111)
        c=create_form("backend","middle",seed=112)
        self.assertEqual(a["items"],b["items"])
        self.assertNotEqual(a["items"],c["items"])

    def test_exposure_uses_unseen_compatible_concept_without_changing_blueprint(self):
        first=create_form("backend","middle",seed=31)
        seen={item["family_id"]:1 for item in first["items"] if item["slot"]=="short"}
        second=create_form("backend","middle",seed=31,exposure=seen)
        first_choices={item["competency"]:item["family_id"] for item in first["items"] if item["slot"]=="short"}
        second_choices={item["competency"]:item["family_id"] for item in second["items"] if item["slot"]=="short"}
        self.assertTrue(all(first_choices[key]!=second_choices[key] for key in first_choices))
        self.assertEqual(len(second["items"]),12)

    def test_unsupported_specialization_and_lead_fail_explicitly(self):
        with self.assertRaises(ValueError): create_form("quantum","middle")
        with self.assertRaises(ValueError): create_form("backend","lead")
        with self.assertRaises(ValueError): create_form("backend","middle",stack=["Java"])

    def test_live_default_rest_api_alias_normalizes_without_certifying_requested_stack(self):
        requested=["Python","SQL","REST API"]
        form=create_form("backend","intern",stack=requested,seed=9)
        self.assertEqual(form["requested_stack"],requested)
        self.assertEqual(form["context_stack"],["Python","SQL","API"])
        self.assertEqual(form["unmeasured_requested_skills"],["Python"])
        self.assertNotIn("Python",form["tested_skills"])
        self.assertEqual(create_form("backend","junior",stack=[" rest   API "],seed=9)["context_stack"],["API"])
        with self.assertRaises(ValueError):create_form("backend","intern",stack=["REST API","Java"],seed=9)

    def test_every_catalog_descriptor_default_and_atomic_context_is_accepted(self):
        for entry in catalog()["specializations"]:
            with self.subTest(specialization=entry["id"]):
                self.assertTrue(entry["allowed_contexts"])
                self.assertTrue(entry["default_contexts"])
                self.assertTrue(set(entry["default_contexts"])<=set(entry["allowed_contexts"]))
                for grade in entry["grades"]:
                    for descriptor in entry["stacks"]:
                        whole=create_form(entry["id"],grade,stack=[descriptor],seed=7)
                        atoms=create_form(entry["id"],grade,stack=descriptor.split("/"),seed=7)
                        self.assertEqual(whole["context_stack"],atoms["context_stack"])
                    self.assertEqual(create_form(entry["id"],grade,stack=entry["default_contexts"],seed=7)["context_stack"],entry["default_contexts"])
                for atomic in entry["allowed_contexts"]:
                    self.assertEqual(create_form(entry["id"],"intern",stack=[atomic],seed=7)["context_stack"],[atomic])

    def test_evidence_only_actual_tasks_not_declared_framework_or_language(self):
        form=create_form("backend","middle",stack=["Python","FastAPI","PostgreSQL"],seed=66)
        answers={item["id"]:reference_answer(item) for item in public_form(form)["items"]}
        result=grade_form(form,answers)
        skills={row["skill"] for row in result["verified_skills"]}
        self.assertIn("SQL",skills)
        for skill in ("Python","FastAPI","PostgreSQL","Redis","Kafka"):
            self.assertNotIn(skill,skills)
        for row in result["verified_skills"]:
            self.assertGreaterEqual(row["item_count"],2)
            self.assertEqual(row["score"],100)
            self.assertEqual(row["strength"],1.)
        self.assertEqual(form["unmeasured_requested_skills"],["Python","FastAPI","PostgreSQL"])

    def test_failed_attempt_does_not_erase_category_and_successful_grade_change_cooldown(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        history=[{"specialization":"backend","grade":"junior","passed":True,"finished_at":(now-timedelta(days=20)).isoformat(),"status":"completed"},{"specialization":"backend","grade":"middle","passed":False,"finished_at":(now-timedelta(days=2)).isoformat(),"status":"completed"}]
        blocked=cooldown_policy(history,"backend","middle",now)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["confirmed_grade"],"junior")
        self.assertEqual(blocked["reason"],"grade_change_90_days")
        self.assertTrue(cooldown_policy(history,"frontend","middle",now)["allowed"])

    def test_failure_lower_grade_and_technical_error_are_separate(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        history=[{"specialization":"backend","grade":"middle","passed":False,"finished_at":(now-timedelta(hours=1)).isoformat(),"status":"completed"}]
        self.assertFalse(cooldown_policy(history,"backend","middle",now)["allowed"])
        self.assertTrue(cooldown_policy(history,"backend","junior",now)["allowed"])
        history[0]["status"]="technical_error"
        self.assertTrue(cooldown_policy(history,"backend","middle",now)["allowed"])

    def test_retest_is_not_new_grade_change(self):
        now=datetime(2026,10,7,tzinfo=timezone.utc)
        history=[{"specialization":"backend","grade":"junior","passed":True,"finished_at":(now-timedelta(days=95)).isoformat(),"status":"completed"},{"specialization":"backend","grade":"junior","passed":True,"finished_at":(now-timedelta(days=10)).isoformat(),"status":"completed"}]
        self.assertTrue(cooldown_policy(history,"backend","middle",now)["allowed"])
        self.assertTrue(cooldown_policy(history,"backend","junior",now)["allowed"])
        history[-1]["finished_at"]=(now-timedelta(days=3)).isoformat()
        self.assertFalse(cooldown_policy(history,"backend","junior",now)["allowed"])
        self.assertTrue(cooldown_policy(history,"backend","middle",now)["allowed"])

    def test_challenge_never_changes_grade_and_unknown_rubric_pending(self):
        private=create_form("backend","junior",seed=80)
        item=next(row for row in private["items"] if row["slot"]=="practice")
        public=next(row for row in public_form(private)["items"] if row["id"]==item["id"])
        result=grade_challenge(item,reference_answer(public))
        self.assertEqual(result["score"],100)
        self.assertFalse(result["category_change"])
        self.assertEqual(grade_challenge({},"x")["status"],"pending_review")


class SQLSafetyTests(unittest.TestCase):
    def setUp(self):
        self.data={"orders":{"columns":{"id":"INTEGER","amount":"INTEGER"},"rows":[[1,10],[2,20],[3,30]]}}

    def test_select_values_use_bounded_separate_dataset(self):
        self.assertEqual(execute_select("SELECT SUM(amount) FROM orders",self.data)["rows"],[[60]])
        self.assertTrue(execute_select("WITH sums AS (SELECT SUM(amount) AS s FROM orders) SELECT s FROM sums",self.data)["ok"])

    def test_mutation_attach_pragma_extensions_and_application_tables_denied(self):
        queries=["DELETE FROM orders","UPDATE orders SET amount=0","DROP TABLE orders","ATTACH DATABASE 'file.db' AS other","PRAGMA table_info(orders)","SELECT load_extension('x')","SELECT * FROM users","SELECT randomblob(99999999)","SELECT 1; SELECT 2","SELECT writefile('attack.txt','pwned')","SELECT * FROM sqlite_master","SELECT readfile('C:/Windows/win.ini')", "SELECT amount FROM данные", "SELECT $injected FROM orders"]
        for query in queries:
            with self.subTest(query=query): self.assertFalse(execute_select(query,self.data)["ok"])
        self.assertEqual(execute_select("SELECT SUM(amount) FROM orders",self.data)["rows"],[[60]])
        # Shell-like characters are ordinary SQL string data: no shell, exec or
        # eval is called. Authorizer protects operations, not keyword blacklists.
        self.assertEqual(execute_select("SELECT '$(' || amount FROM orders",self.data)["rows"],[["$(10"],["$(20"],["$(30"]])

    def test_recursive_vm_and_row_budgets_interrupt(self):
        query="WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<10000000) SELECT SUM(x) FROM n"
        self.assertFalse(execute_select(query,self.data)["ok"])
        query="WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<500) SELECT x FROM n"
        self.assertFalse(execute_select(query,self.data)["ok"])
        query="SELECT COUNT(*) FROM orders a,orders b,orders c,orders d,orders e,orders f,orders g,orders h,orders i,orders j,orders k,orders l"
        self.assertFalse(execute_select(query,self.data)["ok"])


if __name__=="__main__": unittest.main()
