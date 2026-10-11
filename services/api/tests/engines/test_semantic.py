import unittest
from copy import deepcopy
from app.engines.semantic import fit_index,candidate_text,safe_text,MODEL_VERSION
from app.engines.matching import rank_candidates


class SemanticTests(unittest.TestCase):
    def test_actual_cosine_identity_and_unrelated_text(self):
        model=fit_index(("Python SQL API","Docker Linux Kubernetes"))
        self.assertAlmostEqual(model.similarity("Python SQL API",0)["value"],1.,places=5)
        self.assertLess(model.similarity("Python SQL API",1)["value"],.3)
        self.assertEqual(model.metadata["model_version"],MODEL_VERSION)
        self.assertEqual(len(model.metadata["artifact_sha256"]),64)
        self.assertFalse(model.similarity("",0)["supported"])

    def test_artifact_reproducible_and_changes_with_corpus(self):
        first=fit_index(("SQL API","Python"))
        again=fit_index(("SQL API","Python"))
        changed=fit_index(("SQL API","PostgreSQL"))
        self.assertEqual(first.metadata,again.metadata)
        self.assertNotEqual(first.metadata["artifact_sha256"],changed.metadata["artifact_sha256"])

    def test_projection_does_not_include_raw_contacts_resume_or_name(self):
        candidate={"name":"SECRET_NAME","email":"secret@invalid.test","phone":"+79991234567","bio":"RAW_PRIVATE_RESUME","title":"SQL engineer","skills":["SQL"],"evidence":[]}
        text=candidate_text(candidate)
        for secret in ("SECRET_NAME","secret@invalid.test","79991234567","RAW_PRIVATE_RESUME"):
            self.assertNotIn(secret,text)
        self.assertNotIn("secret@invalid.test",safe_text("SQL secret@invalid.test https://private.test +79991234567"))

    def test_semantic_enabled_has_real_feature_but_never_bypasses_grade_gate(self):
        need={"specialization":"backend","grade":"middle","skills":["SQL","Python"],"require_verified_skills":False}
        candidate={"id":"c","specialization":"backend","confirmed_grade":"middle","published":True,"title":"Python SQL","skills":["SQL","Python"],"score":80,"evidence":[],"preferences":{}}
        enabled=rank_candidates(need,[candidate],semantic_enabled=True)[0]
        disabled=rank_candidates(need,[candidate])[0]
        self.assertIn("cpu-tfidf",enabled["algorithm_version"])
        # Both actual output variants must fit the persisted MatchRun VARCHAR(80).
        for result in (enabled,disabled):
            self.assertLessEqual(len(result["algorithm_version"]),80)
        self.assertEqual(enabled["semantic"]["model_version"],MODEL_VERSION)
        self.assertNotEqual(enabled["breakdown"]["semantic"]["value"],disabled["breakdown"]["semantic"]["value"])
        candidate["confirmed_grade"]=None
        self.assertEqual(rank_candidates(need,[candidate],semantic_enabled=True),[])

if __name__=="__main__":unittest.main()
