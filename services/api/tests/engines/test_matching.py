import unittest
from copy import deepcopy
from datetime import datetime,timezone
from app.engines.matching import rank_candidates,admission,evidence_map,explain_exclusion,preference_fit
from app.engines.fsp import demo_link
from app.engines.seed import demo_seed,generate_population,generate_needs

NOW=datetime(2026,10,7,tzinfo=timezone.utc)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.need={"specialization":"backend","grade":"middle","required_skills":["SQL"],"skills":["API"],"salary_from":150000,"salary_to":250000,"work_format":"remote","employment":"full_time"}
        self.candidate={"id":"c-1","specialization":"backend","confirmed_grade":"middle","published":True,"score":90,"skills":["SQL","API","Kubernetes"],"evidence":[{"skill":"SQL","source":"ASSESSMENT_VERIFIED","score":90,"status":"verified","scope":{"specialization":"backend"}},{"skill":"API","source":"ASSESSMENT_VERIFIED","strength":.8,"status":"active"}],"assessment_at":NOW.isoformat(),"preferences":{"salary_from":180000,"salary_to":280000,"work_format":"remote","employment":"full_time"},"fsp":{"status":"not_linked","achievements":[]}}

    def test_formula_and_evidence_only_not_declared_stack(self):
        result=rank_candidates(self.need,[self.candidate],NOW)[0]
        expected=55*((2*.9+.8)/3)+20*.9+10+5+5*.5
        self.assertAlmostEqual(result["score"],round(expected,2))
        self.assertAlmostEqual(sum(row["points"] for row in result["breakdown"].values()),result["score"],places=1)
        self.assertNotIn("candidate",result)
        self.assertEqual(result["score_kind"],"compatibility_index")
        self.candidate["skills"]=["SQL","API","Kubernetes"]*100
        self.assertEqual(rank_candidates(self.need,[self.candidate],NOW)[0]["score"],result["score"])

    def test_admission_never_bypassed_by_fsp_or_score(self):
        cases=[("published",False,"profile_private"),("confirmed_grade",None,"category_unconfirmed"),("confirmed_grade","senior","grade_mismatch"),("specialization","frontend","specialization_mismatch"),("active",False,"account_inactive")]
        for key,value,reason in cases:
            with self.subTest(reason=reason):
                candidate=deepcopy(self.candidate);candidate[key]=value;candidate["score"]=100
                self.assertEqual(rank_candidates(self.need,[candidate],NOW),[])
                self.assertIn(reason,explain_exclusion(self.need,candidate)["reasons"])

    def test_blocked_company_salary_format_and_grant_dont_widen_bank(self):
        candidate=deepcopy(self.candidate);candidate["blocked_companies"]=["co-A"]
        self.assertFalse(admission(self.need,candidate,"co-A")["eligible"])
        self.assertTrue(admission(self.need,candidate,"co-B")["eligible"])
        candidate=deepcopy(self.candidate);candidate["preferences"]["salary_from"]=300000
        self.assertIn("preference_salary",admission(self.need,candidate)["reasons"])
        candidate["preferences"]["strict_salary"]=False
        result=rank_candidates(self.need,[candidate],NOW)[0]
        self.assertLess(result["breakdown"]["preferences"]["points"],10)
        self.assertNotIn("совместимы",next(row["text"] for row in result["reasons"] if row["kind"]=="preferences"))

    def test_offered_any_work_format_matches_each_strict_concrete_preference(self):
        for wildcard in ("any","любой"," ANY "):
            for concrete in ("remote","office","hybrid"):
                for strict in (True,False):
                    with self.subTest(wildcard=wildcard,format=concrete,strict=strict):
                        need=deepcopy(self.need);need["work_format"]=wildcard
                        candidate=deepcopy(self.candidate);candidate["preferences"].update({"work_format":concrete,"strict_work_format":strict})
                        self.assertTrue(admission(need,candidate)["eligible"])
                        self.assertEqual(rank_candidates(need,[candidate],NOW)[0]["breakdown"]["preferences"]["points"],10)
                        # Reverse direction follows the same wildcard semantics.
                        need["work_format"]=concrete;candidate["preferences"]["work_format"]=wildcard
                        self.assertTrue(admission(need,candidate)["eligible"])

    def test_offered_any_employment_matches_each_strict_concrete_preference(self):
        for wildcard in ("any","любой"):
            for concrete in ("full_time","part_time","contract"):
                for strict in (True,False):
                    with self.subTest(wildcard=wildcard,employment=concrete,strict=strict):
                        need=deepcopy(self.need);need["employment"]=wildcard
                        candidate=deepcopy(self.candidate);candidate["preferences"].update({"employment":concrete,"strict_employment":strict})
                        self.assertTrue(admission(need,candidate)["eligible"])
                        self.assertEqual(preference_fit(need,candidate),(1.,[]))
                        need["employment"]=concrete;candidate["preferences"]["employment"]=wildcard
                        self.assertTrue(admission(need,candidate)["eligible"])

    def test_concrete_preferences_still_enforce_strict_flags(self):
        need=deepcopy(self.need);need.update({"work_format":"office","employment":"part_time"})
        candidate=deepcopy(self.candidate);candidate["preferences"].update({"strict_work_format":True,"strict_employment":True})
        self.assertIn("preference_work_format",admission(need,candidate)["reasons"])
        self.assertIn("preference_employment",admission(need,candidate)["reasons"])
        candidate["preferences"].update({"strict_work_format":False,"strict_employment":False})
        self.assertTrue(admission(need,candidate)["eligible"])
        self.assertLess(preference_fit(need,candidate)[0],1.)

    def test_no_preferences_keeps_neutral_and_no_hard_gate(self):
        self.assertEqual(preference_fit({},{}),(.5,[]))
        self.assertEqual(preference_fit({},{"preferences":{}}),(.5,[]))
        self.assertEqual(preference_fit({},{"preferences":{"strict_work_format":True,"strict_employment":True}}),(.5,[]))

    def test_self_declaration_fsp_revoked_wrong_scope_and_missing_score_dont_certify(self):
        for changes in ({"source":"SELF_DECLARED"},{"source":"FSP_DEMO_CONFIRMED"},{"status":"revoked"},{"scope":{"specialization":"frontend"}},{"score":None}):
            candidate=deepcopy(self.candidate);candidate["evidence"][0].update(changes)
            self.assertFalse(admission(self.need,candidate)["eligible"])

    def test_training_allowed_shows_unknown_instead_of_absence(self):
        self.need["required_skills"]=["Rust","Kubernetes"]
        self.need["must_have_mode"]="training_allowed"
        result=rank_candidates(self.need,[self.candidate],NOW)[0]
        gaps={row["skill"]:row["state"] for row in result["gaps"]}
        self.assertEqual(gaps["Rust"],"unknown")
        self.assertEqual(gaps["Kubernetes"],"self_declared_unverified")
        self.assertEqual(result["verified_skills"],["API"])

    def test_fsp_cap_provenance_and_unknown_team_role(self):
        candidate=deepcopy(self.candidate)
        achievement={"title":"Синтетический кубок","specializations":["backend"],"discipline":"Алгоритмы","date":NOW.date().isoformat(),"place":1,"participants":100,"team":False,"status":"active"}
        candidate["fsp"]={"status":"verified_demo","source":"FSP_DEMO_CONFIRMED","achievements":[achievement]*30}
        result=rank_candidates(self.need,[candidate],NOW)[0]
        self.assertGreater(result["breakdown"]["fsp"]["points"],0)
        self.assertLessEqual(result["breakdown"]["fsp"]["points"],5)
        self.assertIn("Демонстрационный",next(row["text"] for row in result["reasons"] if row["kind"]=="fsp"))
        candidate["fsp"]["status"]="sync_stale"
        self.assertEqual(rank_candidates(self.need,[candidate],NOW)[0]["breakdown"]["fsp"]["points"],0)
        candidate["fsp"]["status"]="verified_demo";candidate["fsp"]["source"]="SELF_DECLARED"
        self.assertEqual(rank_candidates(self.need,[candidate],NOW)[0]["breakdown"]["fsp"]["points"],0)

    def test_revoke_publication_rechecks_admission(self):
        self.assertEqual(len(rank_candidates(self.need,[self.candidate],NOW)),1)
        self.candidate["published"]=False
        self.assertEqual(rank_candidates(self.need,[self.candidate],NOW),[])

    def test_stable_tie_break_no_sensitive_feature_effect(self):
        second=deepcopy(self.candidate);second["id"]="c-0";second["email"]="secret@invalid.test";second["name"]="Other"
        result=rank_candidates(self.need,[self.candidate,second],NOW)
        self.assertEqual([row["candidate_id"] for row in result],["c-0","c-1"])
        self.assertEqual(result[0]["score"],result[1]["score"])
        self.assertNotIn("secret@invalid.test",str(result))

    def test_seed_demo_account_unconfirmed_and_fixture_match_available(self):
        dataset=demo_seed()
        current=next(row for row in dataset["candidates"] if row["email"]=="candidate@vector.local")
        self.assertIsNone(current["confirmed_grade"])
        self.assertEqual(current["evidence"],[])
        self.assertFalse(current["published"])
        self.assertGreater(len(rank_candidates(dataset["needs"][0],dataset["candidates"],NOW)),0)

    def test_fsp_demo_identity_owned_no_name_matching(self):
        result=demo_link("FSP-DEMO-001","VECTOR-2026","candidate@vector.local")
        self.assertEqual(result["source"],"FSP_DEMO_CONFIRMED")
        self.assertNotIn("proof_code",str(result))
        with self.assertRaises(ValueError): demo_link("FSP-DEMO-001","VECTOR-2026","employer@vector.local")
        with self.assertRaises(ValueError): demo_link("FSP-DEMO-001","wrong","candidate@vector.local")
        with self.assertRaises(ValueError): demo_link("official-id","VECTOR-2026","candidate@vector.local")

if __name__=="__main__":unittest.main()
