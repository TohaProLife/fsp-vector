import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from evaluation.external import SCHEMA_VERSION,load_dataset,evaluate_dataset,validate_dataset
from app.engines.matching import rank_candidates


def fixture():
    return {"schema_version":SCHEMA_VERSION,"origin":"team_authored_explicit","human_labelers":0,"corpus_origin":"anonymous_fictional_test","needs":[{"id":"n1","specialization":"backend","grade":"middle","required_skills":["SQL"],"skills":[]}],"candidates":[{"id":"c1","specialization":"backend","confirmed_grade":"middle","published":True,"score":90,"evidence":[{"skill":"SQL","source":"ASSESSMENT_VERIFIED","score":90,"scope":{"specialization":"backend","grade":"middle"}}]}],"queries":[{"need_id":"n1","candidate_ids":["c1"]}],"labels":[{"need_id":"n1","candidate_id":"c1","relevance":3}]}


def load(data):
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"labels.json";path.write_text(json.dumps(data),encoding="utf8",newline="\n")
        return load_dataset(path)


class ExternalEvaluationTests(unittest.TestCase):
    def test_explicit_label_hashes_are_reproducible_and_sensitive_to_actual_labels(self):
        data=fixture();first=load(data);second=load(data)
        self.assertEqual(first["input_sha256"],second["input_sha256"])
        self.assertEqual(first["labels_sha256"],second["labels_sha256"])
        changed=deepcopy(data);changed["labels"][0]["relevance"]=0
        third=load(changed)
        self.assertEqual(first["corpus_sha256"],third["corpus_sha256"])
        self.assertNotEqual(first["labels_sha256"],third["labels_sha256"])
        report=evaluate_dataset(first,"2026-10-07T00:00:00Z")
        self.assertEqual(report,evaluate_dataset(second,"2026-10-07T00:00:00Z"))

    def test_duplicate_missing_unknown_ids_and_boolean_labels_fail_closed(self):
        variants=[]
        for field in ("needs","candidates","queries","labels"):
            data=fixture();data[field].append(deepcopy(data[field][0]));variants.append(data)
        data=fixture();data["labels"]=[];variants.append(data)
        data=fixture();data["labels"][0]["candidate_id"]="missing";variants.append(data)
        data=fixture();data["queries"][0]["candidate_ids"].append("missing");variants.append(data)
        data=fixture();data["queries"][0]["candidate_ids"].append("c1");variants.append(data)
        data=fixture();data["labels"][0]["relevance"]=True;variants.append(data)
        data=fixture();data["labels"][0]["relevance"]=4;variants.append(data)
        for data in variants:
            with self.assertRaises(ValueError):load(data)

    def test_nested_malformed_types_nonfinite_duplicates_and_latent_contacts_rejected(self):
        variants=[]
        for field,value in (("specialization",{}),("published","false"),("score",float("nan")),("email","hidden@example.test"),("_latent",{"mastery":1}),("labels",{"c1":3})):
            data=fixture();data["candidates"][0][field]=value;variants.append(data)
        data=fixture();data["queries"][0]["candidate_ids"]=[{}];variants.append(data)
        data=fixture();data["needs"][0]["required_skills"]=[" "];variants.append(data)
        data=fixture();data["candidates"][0]["evidence"][0]["source"]=[];variants.append(data)
        data=fixture();data["candidates"][0]["evidence"][0]["scope"]["specialization"]=[];variants.append(data)
        for data in variants:
            with self.assertRaises(ValueError):load(data)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"duplicate.json";path.write_text('{"schema_version": "a", "schema_version": "b"}',encoding="utf8")
            with self.assertRaisesRegex(ValueError,"duplicate JSON key"):load_dataset(path)
            path.write_bytes(b'\xff\xff')
            with self.assertRaises(ValueError):load_dataset(path)

    def test_zero_eligible_relevant_query_is_retained_and_scores_zero_end_to_end(self):
        data=fixture();data["candidates"][0]["published"]=False
        report=evaluate_dataset(load(data),"2026-10-07T00:00:00Z")
        self.assertEqual(report["queries"],1);self.assertEqual(report["zero_eligible_queries"],1)
        full=report["baselines"]["full_engine"]
        self.assertEqual(full["precision5"]["mean"],0)
        self.assertEqual(full["ndcg10_end_to_end"]["mean"],0)
        self.assertIsNone(full["ndcg10_eligible"]["mean"])
        self.assertEqual(full["ndcg10_eligible"]["undefined_queries"],1)
        self.assertEqual(report["retrieval_recall"]["mean"],0)
        self.assertEqual(report["excluded_relevant_reason_counts"],{"profile_private":1})

    def test_empty_candidate_and_zero_idcg_queries_remain_counted_with_null_metrics(self):
        data=fixture();data["candidates"]=[];data["queries"][0]["candidate_ids"]=[];data["labels"]=[]
        report=evaluate_dataset(load(data),"2026-10-07T00:00:00Z")
        self.assertEqual(report["queries"],1);self.assertEqual(report["pairs"],0)
        self.assertEqual(report["baselines"]["full_engine"]["precision5"]["mean"],0)
        self.assertIsNone(report["baselines"]["full_engine"]["ndcg10_end_to_end"]["mean"])
        self.assertIsNone(report["retrieval_recall"]["mean"])
        self.assertEqual(report["retrieval_recall"]["retained_queries"],1)
        data=fixture();data["labels"][0]["relevance"]=0
        report=evaluate_dataset(load(data),"2026-10-07T00:00:00Z")
        self.assertEqual(report["baselines"]["full_engine"]["ndcg10_end_to_end"]["undefined_queries"],1)
        self.assertEqual(report["zero_eligible_queries"],0)

    def test_fixed_precision_denominator_and_declared_humans_are_not_pilot_claim(self):
        data=fixture();data.update(origin="external_human",human_labelers=2,label_metadata={"procedure":"Declared independent anonymous annotation","blinded_to_scores":True})
        report=evaluate_dataset(load(data),"2026-10-07T00:00:00Z")
        self.assertEqual(report["baselines"]["full_engine"]["precision5"]["mean"],.2)
        self.assertEqual(report["baselines"]["full_engine"]["ndcg10_end_to_end"]["mean"],1)
        self.assertEqual(report["declared_human_labelers"],2)
        self.assertFalse(report["human_pilot_claimed"]);self.assertFalse(report["origin_independently_verified"])
        data["human_labelers"]=0
        with self.assertRaises(ValueError):load(data)

    def test_labels_never_reach_matcher_and_loaded_corpus_mutation_is_rejected(self):
        loaded=load(fixture())
        with patch("evaluation.external.rank_candidates",wraps=rank_candidates) as matcher:
            evaluate_dataset(loaded,"2026-10-07T00:00:00Z")
            passed_profiles=matcher.call_args.args[1]
            self.assertNotIn("labels",str(passed_profiles));self.assertNotIn("_latent",str(passed_profiles))
        loaded["data"]["labels"][0]["relevance"]=0
        with self.assertRaisesRegex(ValueError,"changed after immutable hashing"):evaluate_dataset(loaded)


if __name__=="__main__":unittest.main()
