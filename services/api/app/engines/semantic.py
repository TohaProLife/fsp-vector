"""Optional CPU text retrieval baseline: word + character TF-IDF/cosine.

This is a real computed lexical model, NOT a language model or a claim of deep
semantic understanding. It requires no remote API, model download or GPU. Public
ranking calls expose algorithm and corpus artifact hashes and preserve admission.
"""

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from .taxonomy import SKILL_ALIASES

MODEL_VERSION="vector-cpu-word-char-tfidf-v1"
PARAMETERS={"word_weight":.7,"character_weight":.3,"char_ngram_range":[3,4],"max_text_chars":4000,"max_char_source_chars":384,"max_documents":5000,"max_vocabulary":40000,"sublinear_tf":True,"smooth_idf":True,"normalization":"l2"}
STOPWORDS={"и","в","на","по","для","с","из","или","как","это","что","the","and","of","for","to","a","an","with","вымышленный","демонстрационный","synthetic","profile","профиль","данные"}


def safe_text(text):
    text=str(text or "")[:PARAMETERS["max_text_chars"]]
    text=re.sub(r"https?://\S+|[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}|(?:\+?\d[\s()-]*){8,}"," ",text,flags=re.I)
    return text


def _terms(text):
    cleaned=safe_text(text).casefold().replace("ё","е")
    # Canonical synonyms are fixed vocabulary, not a learned ability inference.
    for alias,canonical in sorted(SKILL_ALIASES.items(),key=lambda row:-len(row[0])):
        cleaned=re.sub(r"(?<!\w)"+re.escape(alias)+r"(?!\w)",canonical.casefold(),cleaned)
    words=[word for word in re.findall(r"[a-zа-я0-9][a-zа-я0-9+#.-]*",cleaned) if len(word)>1 and word not in STOPWORDS]
    counts=Counter("w:"+word for word in words)
    chars=" ".join(words)[:PARAMETERS["max_char_source_chars"]]
    for n in PARAMETERS["char_ngram_range"]:
        counts.update("c:"+chars[index:index+n] for index in range(max(0,len(chars)-n+1)) if chars[index:index+n].strip())
    return counts


def _vector(counts,idf):
    values={term:(1+math.log(count))*idf[term]*(PARAMETERS["word_weight"] if term.startswith("w:") else PARAMETERS["character_weight"]) for term,count in counts.items() if term in idf}
    norm=math.sqrt(sum(value*value for value in values.values()))
    return {term:value/norm for term,value in values.items()} if norm else {}


@dataclass
class TfidfIndex:
    idf:dict
    vectors:list
    metadata:dict

    def similarity(self,text,index):
        query=_vector(_terms(text),self.idf)
        candidate=self.vectors[index]
        similarity=sum(value*candidate.get(term,0.) for term,value in query.items())
        known=len(query); unsupported=not query or not candidate
        return {"value":round(min(1.,max(0.,similarity)),6),"supported":not unsupported,"status":"unsupported_empty_or_unknown_text" if unsupported else "calculated_lexical_similarity","known_feature_count":known,"model_version":MODEL_VERSION,"artifact_sha256":self.metadata["artifact_sha256"],"confidence":"lexical_baseline_uncalibrated","is_llm":False}


@lru_cache(maxsize=8)
def fit_index(texts:tuple[str,...]) -> TfidfIndex:
    if len(texts)>PARAMETERS["max_documents"]:
        raise ValueError("TF-IDF corpus exceeds configured document budget")
    counts=[_terms(text) for text in texts]
    frequency=Counter(term for row in counts for term in row)
    top=sorted(frequency,key=lambda term:(-frequency[term],term))[:PARAMETERS["max_vocabulary"]]
    idf={term:math.log((1+len(texts))/(1+frequency[term]))+1 for term in top}
    vectors=[_vector(row,idf) for row in counts]
    corpus_hash=hashlib.sha256(json.dumps([safe_text(text) for text in texts],ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
    artifact_hash=hashlib.sha256(json.dumps({"version":MODEL_VERSION,"parameters":PARAMETERS,"idf":idf,"corpus":corpus_hash},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    return TfidfIndex(idf,vectors,{"model_version":MODEL_VERSION,"artifact_sha256":artifact_hash,"corpus_sha256":corpus_hash,"documents":len(texts),"vocabulary":len(idf),"parameters":PARAMETERS,"semantic_scope":"lexical_similarity_only","empirical_hiring_validation":"NOT_MEASURED"})


def candidate_text(candidate):
    # Free resume/contact/name is deliberately absent. Only safe role/skill context
    # supports recall; a lexical match still cannot create assessment evidence.
    skills=candidate.get("skills") or []
    evidence=candidate.get("evidence") or []
    return safe_text(" ".join([str(candidate.get("specialization","")),str(candidate.get("title",""))," ".join(str(skill) for skill in skills)," ".join(str(row.get("skill","")) for row in evidence if isinstance(row,dict) and row.get("source")=="ASSESSMENT_VERIFIED")]))


def need_text(need):
    return safe_text(" ".join([str(need.get("specialization","")),str(need.get("title",""))," ".join(str(skill) for skill in need.get("required_skills",[]))," ".join(str(skill) for skill in need.get("skills",[])),str(need.get("description",""))]))
