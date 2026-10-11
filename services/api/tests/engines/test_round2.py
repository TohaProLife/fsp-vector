import hashlib
import json
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone

from app.engines.assessment import create_form,public_form,grade_form,cooldown_policy,need_blueprint,generate_need_assessment
from app.engines.matching import admission,rank_candidates,freshness_signal,candidate_fit_actions
from app.engines.taxonomy import SPECIALIZATIONS
from app.engines.extraction import extract_need
from evaluation.reference_solvers import reference_answer

NOW=datetime(2026,10,7,tzinfo=timezone.utc)


class Round2AssessmentTests(unittest.TestCase):
    def test_every_advanced_family_critical_error_is_independently_rejected(self):
        seen=set()
        for spec in SPECIALIZATIONS:
            for grade in ("middle","senior"):
                form=create_form(spec,grade,seed=88431)
                answers={item["id"]:reference_answer(item) for item in public_form(form)["items"]}
                for item in form["items"]:
                    if not item.get("advanced"):continue
                    wrong=deepcopy(answers)
                    if item["type"]=="sql":wrong[item["id"]]="SELECT 999999"
                    else:wrong[item["id"]][item["_oracle"]["critical"][0]]={"incorrect_shape":True}
                    result=grade_form(form,wrong)
                    feedback=next(row for row in result["feedback"] if row["item_id"]==item["id"])
                    self.assertLessEqual(feedback["earned_score"],4)
                    self.assertFalse(result["passed"])
                    seen.add(item["family_id"])
        self.assertEqual(len(seen),22)

    def test_json_depth_text_size_and_overflow_are_wrong_answers_not_exceptions(self):
        form=create_form("data","middle",seed=8823)
        answers={item["id"]:reference_answer(item) for item in public_form(form)["items"]}
        item=next(item for item in form["items"] if item.get("public_cases",{}).get("advanced_mode")=="stratified-effect")
        for value in (10**1000,"x"*20000,[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]):
            wrong=deepcopy(answers);wrong[item["id"]]["raw_delta_pp"]=value
            self.assertFalse(grade_form(form,wrong)["score"]==100)
    def test_advanced_failure_cannot_be_compensated_by_generic_success(self):
        for spec in SPECIALIZATIONS:
            for grade in ("middle","senior"):
                form=create_form(spec,grade,seed=836)
                public=public_form(form)
                answers={item["id"]:reference_answer(item) for item in public["items"]}
                advanced=[item for item in form["items"] if item.get("advanced")]
                self.assertEqual(len(advanced),4)
                for item in advanced:
                    partial=deepcopy(answers);partial.pop(item["id"])
                    result=grade_form(form,partial)
                    self.assertGreater(result["score"],90)
                    self.assertFalse(result["passed"])
                    self.assertIn("advanced_competency",result["failed_floors"])
                    self.assertEqual(result["verified_skills"],[])

    def test_critical_wrong_field_caps_score_and_disallows_extra_keys_bool_number(self):
        form=create_form("backend","senior",seed=91)
        public=public_form(form)
        answers={item["id"]:reference_answer(item) for item in public["items"]}
        item=next(item for item in form["items"] if item["_oracle"]["kind"]=="rubric_json")
        correct=answers[item["id"]]
        partial=deepcopy(answers);partial[item["id"]]=deepcopy(correct)
        partial[item["id"]][item["_oracle"]["critical"][0]]="invalid critical value"
        feedback=next(row for row in grade_form(form,partial)["feedback"] if row["item_id"]==item["id"])
        self.assertLessEqual(feedback["earned_score"],4)
        self.assertFalse(grade_form(form,partial)["passed"])
        partial[item["id"]]={**correct,"oracle":"guessed"}
        self.assertEqual(next(row for row in grade_form(form,partial)["feedback"] if row["item_id"]==item["id"])["earned_score"],0)
        total_item=next(item for item in form["items"] if item.get("public_cases",{}).get("advanced_mode")=="event-ledger")
        partial=deepcopy(answers);partial[total_item["id"]]["total"]=True
        self.assertLess(next(row for row in grade_form(form,partial)["feedback"] if row["item_id"]==total_item["id"])["earned_score"],10)

    def test_stored_old_policy_is_not_changed_retroactively(self):
        form=create_form("backend","senior",seed=91)
        answers={item["id"]:reference_answer(item) for item in public_form(form)["items"]}
        missing=next(item for item in form["items"] if item.get("advanced"))
        answers.pop(missing["id"])
        self.assertFalse(grade_form(form,answers)["passed"])
        old=deepcopy(form);old["rubric_version"]="vector-rubric-70-50-60-v1"
        old["policy"]={"pass_score":70,"competency_minimum":50,"practice_minimum":60}
        self.assertTrue(grade_form(old,answers)["passed"])

    def test_need_snapshot_context_stays_private_and_unmeasured_skills_remain_unknown(self):
        need={"id":"n1","specialization":"backend","grade":"senior","description":"Python, SQL, API; PostgreSQL будет плюсом.","skills":["Python","PostgreSQL","API"],"required_skills":["SQL","Python"],"private_contact":"secret@private.test"}
        mapping=need_blueprint(need)
        self.assertEqual(mapping["tested_skills"],["SQL","API"])
        self.assertEqual(mapping["unmeasured_skills"],["Python","PostgreSQL"])
        self.assertEqual(need_blueprint(dict(reversed(list(need.items()))))["need_snapshot_sha256"],mapping["need_snapshot_sha256"])
        changed=deepcopy(need);changed["required_skills"]=["API"]
        self.assertNotEqual(need_blueprint(changed)["need_snapshot_sha256"],mapping["need_snapshot_sha256"])
        envelope=generate_need_assessment(need,seed=991)
        private=envelope.pop("private_payload");public=public_form(private)
        self.assertNotIn("secret@private.test",json.dumps(public))
        self.assertNotIn("_oracle",json.dumps(public))
        self.assertNotIn("need_snapshot\"",json.dumps(public))
        private["context"]["_secret"]={"oracle":"__NOT_PUBLIC_991__"}
        private["context"]["competencies"][0]["_answer"]="__NOT_PUBLIC_991__"
        self.assertNotIn("__NOT_PUBLIC_991__",json.dumps(public_form(private)))
        answers={item["id"]:reference_answer(item) for item in public["items"]}
        result=grade_form(private,answers)
        self.assertTrue(result["passed"])
        self.assertIsNone(result["confirmed_grade"])
        self.assertFalse(result["category_change_allowed"])
        self.assertEqual(result["evidence_source"],"NEED_PRACTICE_OBSERVED")
        self.assertTrue(all(row["source"]=="NEED_PRACTICE_OBSERVED" for row in result["verified_skills"]))
        self.assertFalse({"Python","PostgreSQL"}&{row["skill"] for row in result["verified_skills"]})
        history=[{"specialization":"backend","grade":"senior","passed":True,"finished_at":NOW.isoformat(),"context":mapping}]
        self.assertTrue(cooldown_policy(history,"backend","middle",NOW)["allowed"])

    def test_distinct_need_descriptions_map_without_hidden_weights(self):
        descriptions=[("Backend Middle. Обязательны SQL и API, Python будет плюсом.","backend","middle",{"SQL","API"}), ("Data analyst Senior: SQL и статистика. pandas будет плюсом.","data","senior",{"SQL","Статистика"}), ("Frontend Junior. Требуется a11y, React будет плюсом.","frontend","junior",{"Доступность"})]
        for text,spec,grade,measured in descriptions:
            mapping=need_blueprint({"description":text})
            self.assertEqual(mapping["specialization"],spec);self.assertEqual(mapping["grade"],grade)
            self.assertEqual(set(mapping["tested_skills"]),measured)
            self.assertEqual(sum(row["item_count"] for row in mapping["competencies"]),12)
            self.assertEqual(mapping["blueprint_rule"],"fixed_common_blueprint_no_hidden_employer_weights")
        with self.assertRaises(ValueError):need_blueprint({"description":"Backend или frontend, junior или senior"})
        with self.assertRaises(ValueError):need_blueprint({"specialization":"backend","grade":"lead"})


class Round2MatchingTests(unittest.TestCase):
    def test_company_need_practice_affects_only_owner_company_and_never_required_proof(self):
        self.candidate["evidence"]=self.candidate["evidence"][:1]
        baseline=rank_candidates(self.need,[self.candidate],NOW,company_id="B")[0]
        observation={"skill":"API","source":"NEED_PRACTICE_OBSERVED","score":100,"objectively_graded":True,"confirmed_at":NOW.isoformat(),"scope":{"specialization":"backend","company_id":"A","global_grade":False}}
        self.candidate["evidence"].append(observation)
        own=rank_candidates(self.need,[self.candidate],NOW,company_id="A")[0]
        other=rank_candidates(self.need,[self.candidate],NOW,company_id="B")[0]
        self.assertGreater(own["score"],baseline["score"])
        self.assertEqual(other["score"],baseline["score"])
        self.assertEqual(other["freshness"]["observations"],[])
        self.assertNotIn("NEED_PRACTICE_OBSERVED",json.dumps(other["reasons"]))
        self.assertEqual(rank_candidates(self.need,[self.candidate],NOW)[0]["score"],baseline["score"])
        self.candidate["evidence"][0]["source"]="NEED_PRACTICE_OBSERVED"
        self.candidate["evidence"][0].update(objectively_graded=True,scope={"specialization":"backend","company_id":"A","global_grade":False})
        self.assertFalse(admission(self.need,self.candidate,company_id="A")["eligible"])

    def test_global_weekly_practice_remains_available_and_company_binding_fails_closed(self):
        practice={"skill":"API","source":"PRACTICE_OBSERVED","score":100,"objectively_graded":True,"confirmed_at":NOW.isoformat(),"scope":{"specialization":"backend"}}
        self.candidate["evidence"].append(practice)
        self.assertEqual(rank_candidates(self.need,[self.candidate],NOW,company_id="A")[0]["score"],rank_candidates(self.need,[self.candidate],NOW,company_id="B")[0]["score"])
        practice["source"]="NEED_PRACTICE_OBSERVED"
        self.assertEqual(freshness_signal(self.need,self.candidate,NOW,"A")["practice_bonus"],0)
    def test_counterfactual_advice_never_invents_evidence_or_changes_profile(self):
        original=deepcopy(self.candidate)
        advice=candidate_fit_actions(self.need,self.candidate,NOW)
        self.assertEqual(original,self.candidate)
        self.assertTrue(all(action["claim"]=="conditional" for action in advice["actions"]))
        self.need["required_skills"]=["Python"]
        advice=candidate_fit_actions(self.need,self.candidate,NOW)
        self.assertFalse(advice["current_fit"]["eligible"])
        self.assertTrue(any(action["kind"]=="unmeasured_requirement" and action["estimated_delta"] is None for action in advice["actions"]))
        self.assertEqual(original,self.candidate)

    def test_preference_only_advice_delta_is_calculated_with_same_hard_gates(self):
        self.need["work_format"]="office"
        self.candidate["preferences"]={"work_format":"remote","strict_work_format":False}
        advice=candidate_fit_actions(self.need,self.candidate,NOW)
        action=next(action for action in advice["actions"] if action["kind"]=="preference_compatibility")
        before=rank_candidates(self.need,[self.candidate],NOW)[0]["score"]
        candidate=deepcopy(self.candidate);candidate["preferences"]["work_format"]="office"
        after=rank_candidates(self.need,[candidate],NOW)[0]["score"]
        self.assertEqual(action["estimated_delta"],round(after-before,2))
        self.assertEqual(candidate["evidence"],self.candidate["evidence"])
    def setUp(self):
        self.need={"specialization":"backend","grade":"senior","required_skills":["SQL"],"skills":["API"],"work_format":"any"}
        self.candidate={"id":"test","published":True,"specialization":"backend","confirmed_grade":"senior","score":100,"assessment_at":(NOW-timedelta(days=365)).isoformat(),"evidence":[{"skill":"SQL","source":"ASSESSMENT_VERIFIED","score":50,"scope":{"specialization":"backend","grade":"senior"}},{"skill":"API","source":"ASSESSMENT_VERIFIED","score":100}],"preferences":{"work_format":"remote"}}

    def test_practice_and_manual_review_never_replace_required_formal_evidence(self):
        for source in ("PRACTICE_OBSERVED","NEED_PRACTICE_OBSERVED","EMPLOYER_REVIEW","SELF_DECLARED"):
            candidate=deepcopy(self.candidate);candidate["evidence"][0].update(source=source,score=100,objectively_graded=True)
            self.assertFalse(admission(self.need,candidate)["eligible"])
        candidate=deepcopy(self.candidate);candidate["evidence"][0]["scope"]["grade"]="junior"
        self.assertFalse(admission(self.need,candidate)["eligible"])
        self.need["required_min_strength"]=.8
        self.assertFalse(admission(self.need,self.candidate)["eligible"])
        self.need["required_min_strength"]=.1
        self.assertTrue(admission(self.need,self.candidate)["eligible"])

    def test_weak_required_limits_coverage_even_with_many_perfect_optional_skills(self):
        self.need["skills"]=[f"nice-{i}" for i in range(40)]
        self.candidate["evidence"] += [{"skill":skill,"source":"ASSESSMENT_VERIFIED","score":100} for skill in self.need["skills"]]
        result=rank_candidates(self.need,[self.candidate],NOW)[0]
        self.assertEqual(result["breakdown"]["competencies"]["value"],.75)
        self.assertTrue(any(row["kind"]=="weakest_required" for row in result["reasons"]))
        self.candidate["evidence"][0]["score"]=49
        self.assertEqual(rank_candidates(self.need,[self.candidate],NOW),[])

    def test_only_recent_relevant_objective_scored_practice_changes_freshness(self):
        practice={"skill":"SQL","source":"PRACTICE_OBSERVED","score":100,"objectively_graded":True,"confirmed_at":NOW.isoformat(),"scope":{"specialization":"backend"}}
        candidate=deepcopy(self.candidate);candidate["evidence"].append(practice)
        base=rank_candidates(self.need,[self.candidate],NOW)[0]
        improved=rank_candidates(self.need,[candidate],NOW)[0]
        self.assertEqual(improved["score"]-base["score"],1.25)
        self.assertEqual(improved["breakdown"]["competencies"],base["breakdown"]["competencies"])
        self.assertEqual(improved["verified_skills"],base["verified_skills"])
        for change in ({"score":None},{"score":59},{"score":True},{"objectively_graded":False},{"skill":"Rust"},{"scope":{"specialization":"frontend"}},{"source":"EMPLOYER_REVIEW"},{"status":"revoked"},{"confirmed_at":(NOW+timedelta(seconds=1)).isoformat()},{"confirmed_at":(NOW-timedelta(days=90)).isoformat()}):
            candidate=deepcopy(self.candidate);candidate["evidence"].append({**practice,**change})
            self.assertEqual(freshness_signal(self.need,candidate,NOW)["practice_bonus"],0)


class Round2ExtractionTests(unittest.TestCase):
    def test_neighbor_predicate_does_not_negate_another_skill(self):
        result=extract_need("Python обязателен и SQL не требуется.")
        self.assertEqual(result["required_skills"],["Python"])
        self.assertEqual(result["excluded_skills"],["SQL"])

    def test_collective_list_polarity_and_not_only(self):
        result=extract_need("Не требуются Python, SQL и Docker.")
        self.assertEqual(set(result["excluded_skills"]),{"Python","SQL","Docker"})
        self.assertEqual(result["required_skills"],[])
        result=extract_need("Не только Python, но и SQL обязателен.")
        self.assertEqual(set(result["required_skills"]),{"Python","SQL"})
        self.assertEqual(result["excluded_skills"],[])


if __name__=="__main__":unittest.main()
