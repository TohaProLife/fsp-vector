import unittest
from copy import deepcopy
from datetime import datetime,timezone
from app.engines.matching import fsp_signal,rank_candidates
from app.engines.assessment import create_form,public_form,grade_form
from app.engines.taxonomy import SPECIALIZATIONS,GRADES
from evaluation.responders import fixed_profiles,respond,misconception_answer
from evaluation.stability import paired_metrics,item_metrics,pearson

NOW=datetime(2026,10,7,tzinfo=timezone.utc)


class ExpertFSPTests(unittest.TestCase):
    def candidate(self,discipline,scopes=None):
        return {"id":"c","published":True,"specialization":"security","confirmed_grade":"middle","score":90,"fsp":{"status":"verified_demo","source":"FSP_DEMO_CONFIRMED","achievements":[{"event_id":"event","title":"Fictional event","discipline":discipline,"specializations":scopes or [],"date":NOW.isoformat(),"place":1,"participants":100,"team":False,"status":"active"}]}}

    def test_all_disciplines_and_mismatched_scope_receive_equal_sport_base(self):
        for spec in SPECIALIZATIONS:
            signals=[]
            for discipline in ("Robotics","Product programming","Unknown discipline"):
                signal,detail=fsp_signal(self.candidate(discipline,["data"]),spec,NOW)
                # Scope relevance is optional: mismatch must never remove base.
                expected=.6*(1. if spec=="data" else .8)
                self.assertAlmostEqual(signal,expected)
                self.assertEqual(detail[0]["sport_base_coefficient"],.8)
                signals.append(signal)
            self.assertEqual(len(set(signals)),1)

    def test_optional_relevance_explained_and_symmetric_without_discipline_hierarchy(self):
        unrelated,detail=fsp_signal(self.candidate("Robotics"),"security",NOW)
        relevant,related_detail=fsp_signal(self.candidate("CTF"),"security",NOW)
        declared,scope_detail=fsp_signal(self.candidate("Robotics",["security"]),"security",NOW)
        self.assertAlmostEqual(unrelated,.48)
        self.assertAlmostEqual(relevant,.6)
        self.assertEqual(relevant,declared)
        self.assertEqual(detail[0]["relevance_basis"],"equal_sport_base")
        self.assertEqual(related_detail[0]["context_bonus_coefficient"],.2)
        self.assertEqual(scope_detail[0]["relevance_basis"],"verified_specialization_scope")

    def test_new_base_never_changes_gate_or_validity_and_cap_survives(self):
        need={"specialization":"security","grade":"middle"}
        candidate=self.candidate("Robotics",["frontend"])
        row=rank_candidates(need,[candidate],NOW)[0]
        self.assertEqual(row["breakdown"]["fsp"]["discipline_policy"],"equal_base_optional_role_relevance")
        self.assertAlmostEqual(row["breakdown"]["fsp"]["points"],2.4)
        for field,value in (("confirmed_grade",None),("confirmed_grade","senior"),("published",False)):
            changed=deepcopy(candidate);changed[field]=value
            self.assertEqual(rank_candidates(need,[changed],NOW),[])
        for changes in ({"status":"revoked"},{"place":0},{"participants":0}):
            changed=deepcopy(candidate);changed["fsp"]["achievements"][0].update(changes)
            self.assertEqual(fsp_signal(changed,"security",NOW)[0],0)
        candidate["fsp"]["achievements"]*=20
        self.assertAlmostEqual(fsp_signal(candidate,"security",NOW)[0],.48)
        for index in range(50):candidate["fsp"]["achievements"].append({**candidate["fsp"]["achievements"][0],"event_id":str(index)})
        self.assertLessEqual(rank_candidates(need,[candidate],NOW)[0]["breakdown"]["fsp"]["points"],5)


class SyntheticStudyTests(unittest.TestCase):
    def test_kappa_independent_hand_confusion_and_undefined_controls(self):
        pairs=[({"category":a,"score":x},{"category":b,"score":y}) for a,b,x,y in (("middle","middle",90,95),("middle","UNCONFIRMED",80,60),("UNCONFIRMED","middle",50,75),("UNCONFIRMED","UNCONFIRMED",40,45))]
        result=paired_metrics(pairs)
        self.assertEqual(result["agreement"],.5)
        self.assertEqual(result["expected_agreement"],.5)
        self.assertEqual(result["kappa"],0.)
        self.assertEqual(result["mean_absolute_score_difference"],13.75)
        identical=paired_metrics([({"category":"middle","score":100},{"category":"middle","score":100})]*4)
        self.assertIsNone(identical["kappa"])
        self.assertIsNone(identical["score_correlation"])
        self.assertEqual(identical["agreement"],1)

    def test_item_rest_removes_self_correlation_and_upper_lower_uses_rest(self):
        constant_rest=[{"fraction":score,"rest":50,"profile":str(index),"repeat":0} for index,score in enumerate((0,1,0,1))]
        result=item_metrics(constant_rest)
        self.assertIsNone(result["corrected_item_rest_correlation"])
        self.assertIsNone(result["upper_lower_difference"])
        self.assertGreater(result["item_variance"],0)
        increasing=[{"fraction":i/7,"rest":i*10,"profile":str(i),"repeat":0} for i in range(8)]
        result=item_metrics(increasing)
        self.assertEqual(result["corrected_item_rest_correlation"],1)
        self.assertAlmostEqual(result["upper_lower_difference"],6/7,places=6)
        self.assertEqual(pearson([1,2,3],[3,2,1]),-1)

    def test_responders_consume_public_conditions_and_use_real_ordinary_grader(self):
        for spec,definition in SPECIALIZATIONS.items():
            profiles=fixed_profiles(definition["competencies"])
            self.assertEqual(len(profiles),20)
            for grade in GRADES:
                private=create_form(spec,grade,seed=2026100704);public=public_form(private)
                perfect=profiles[0]
                answers={item["id"]:respond(item,perfect) for item in public["items"]}
                self.assertEqual(grade_form(private,answers)["score"],100)
                for item in public["items"]:
                    for profile in profiles:respond(item,profile)
                private_before=deepcopy(private)
                weak={item["id"]:respond(item,profiles[2]) for item in public["items"]}
                grade_form(private,weak)
                self.assertEqual(private,private_before)

    def test_fixed_behavior_is_invariant_to_answer_keys_item_ids_and_option_order(self):
        item=public_form(create_form("backend","middle",seed=2026100704))["items"][0]
        for profile in fixed_profiles(SPECIALIZATIONS["backend"]["competencies"]):
            changed=deepcopy(item);changed["id"]="changed";changed["_oracle"]={"expected":"poison"}
            if item["type"]=="single_choice":changed["options"].reverse()
            self.assertEqual(respond(item,profile),respond(changed,profile))
        # Arrival-order misconception depends on data, not a wrong-score oracle.
        task={"type":"json","public_cases":{"events":[{"entity":"a","version":2,"value":20},{"entity":"a","version":1,"value":10}]}}
        self.assertEqual(misconception_answer(task),{"a":10})
        task["public_cases"]["events"].reverse()
        self.assertEqual(misconception_answer(task),{"a":20})


if __name__=="__main__":unittest.main()
