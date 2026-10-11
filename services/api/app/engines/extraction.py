"""Rules baseline: extract a draft with quoted spans, never infer verified skills."""

import re
from .taxonomy import CANONICAL_VALUES, SKILL_ALIASES

EXTRACTION_VERSION="vector-need-rules-3-phrase-list-scope"
MAX_TEXT=20_000
OPTIONAL=r"(?:не\s+обязател\w*|желател\w*|буд(?:ет|ут)\s+плюсом|приветств\w*|nice.?to.?have|optional|preferred)"
NEGATIVE=r"(?:не\s+(?:требу\w*|нуж\w*|использ\w*)|без\s+опыт\w*|not\s+required|не\s+планир\w*)"
LIST_CONNECTOR=r"[\s,]*(?:(?:и|или|and|or)[\s,]*)?"


def _span(text,start,end,field,value,polarity="required"):
    return {"field":field,"value":value,"start":start,"end":end,"quote":text[start:end],"polarity":polarity,"source":"rule_extraction","confidence":"rule"}


def _clause(text,start,end):
    left=max(text.rfind(mark,0,start) for mark in (".",";","\n","!","?"))+1
    ends=[text.find(mark,end) for mark in (".",";","\n","!","?")]
    right=min([value for value in ends if value>=0] or [len(text)])
    return text[left:right].casefold(),start-left,end-left,left,right


def _suffix_polarity(value):
    # This is a predicate of the last member of a bare connected list. A comma
    # or contrast after it starts another statement and must stop propagation.
    value=re.split(r"\b(?:но|а|but)\b|,",value)[0]
    if re.search(OPTIONAL,value):return "preferred"
    if re.search(NEGATIVE,value):return "excluded"
    return None


def _list_suffix(text,mentions,index,clause_right):
    last=index
    while last+1<len(mentions) and mentions[last+1][0]<clause_right:
        connector=text[mentions[last][1]:mentions[last+1][0]].casefold()
        if not re.fullmatch(LIST_CONNECTOR,connector):break
        last+=1
    if last==index:return None
    end=mentions[last][1]
    next_start=mentions[last+1][0] if last+1<len(mentions) else clause_right
    return _suffix_polarity(text[end:min(clause_right,next_start,end+55)].casefold())


def _polarity(clause,relative_start,relative_end,previous_end=0,next_start=None,previous_polarity=None,list_suffix=None):
    before=clause[max(previous_end,relative_start-55):relative_start]
    after=clause[relative_end:min(next_start if next_start is not None else len(clause),relative_end+55)]
    # Associate the closest marker with the mentioned token, avoiding another
    # list member's negation across a contrast delimiter.
    connector=before
    before=re.split(r"\b(?:но|а|but)\b|,",before)[-1]
    after=re.split(r"\b(?:но|а|but)\b|,",after)[0]
    if re.search(OPTIONAL,before) or re.search(OPTIONAL,after): return "preferred"
    if re.search(NEGATIVE,before) or re.search(NEGATIVE,after): return "excluded"
    if list_suffix:return list_suffix
    # A leading list marker governs subsequent bare list members. A predicate
    # attached to a different named skill does not propagate across that skill.
    if previous_polarity and re.fullmatch(LIST_CONNECTOR,connector):return previous_polarity
    return "required"


def extract_need(text:str) -> dict:
    if not isinstance(text,str) or len(text)>MAX_TEXT:
        raise ValueError("Описание должно быть строкой до 20 000 символов.")
    spans=[]; skills=[]; required=[]; preferred=[]; excluded=[]; used=[];mentions=[]
    # Measured concept names are first-class phrases, not a certification of a
    # shorter technology substring (JavaScript concepts != JavaScript).
    phrases={**SKILL_ALIASES,**CANONICAL_VALUES}
    for alias,canonical in sorted(phrases.items(),key=lambda item:(-len(item[0]),item[0])):
        pattern=r"(?<![\w])"+re.escape(alias)+r"(?![\w])"
        for match in re.finditer(pattern,text,re.I):
            if any(match.start()<end and match.end()>start for start,end in used): continue
            used.append((match.start(),match.end()))
            mentions.append((match.start(),match.end(),canonical))
    mentions.sort()
    previous=None
    for index,(mention_start,mention_end,canonical) in enumerate(mentions):
            clause,start,end,left,right=_clause(text,mention_start,mention_end)
            previous_end=previous[1]-left if previous and previous[0]>=left else 0
            previous_polarity=previous[2] if previous and previous[0]>=left else None
            next_start=mentions[index+1][0]-left if index+1<len(mentions) and mentions[index+1][0]<right else None
            polarity=_polarity(clause,start,end,previous_end,next_start,previous_polarity,_list_suffix(text,mentions,index,right))
            target=excluded if polarity=="excluded" else preferred if polarity=="preferred" else required
            if canonical not in target: target.append(canonical)
            if polarity!="excluded" and canonical not in skills: skills.append(canonical)
            spans.append(_span(text,mention_start,mention_end,"skill",canonical,polarity))
            previous=(mention_start,mention_end,polarity)
    # Conflicting mentions are visible and require confirmation, never resolved
    # silently by whichever regex happened to run last.
    conflicts=sorted(set(required)&set(excluded) | set(preferred)&set(excluded))
    patterns=[("backend",r"\bbackend\b|бэкенд|бекенд|серверн\w*\s+разработ"),("frontend",r"\bfrontend\b|фронтенд|фронтэнд"),("qa",r"\bqa\b|тестировщик|инженер\s+тестирован"),("devops",r"\bdevops\b|\bsre\b"),("data",r"data\s+analyst|аналитик\s+данных|data\s+analytics"),("security",r"\bsecurity\b|(?:инженер|специалист|аналитик|архитектор)\w*\s+по\s+(?:информационн\w*\s+)?безопасност\w*")]
    spec_matches=[]
    for value,pattern in patterns:
        # A direction name inside a recognized skill phrase is not a second
        # hiring role. Search later matches too, so an explicit Security role
        # after a Web security mention is still represented as ambiguous.
        match=next((candidate for candidate in re.finditer(pattern,text,re.I) if not any(candidate.start()<end and candidate.end()>start for start,end in used)),None)
        if match:
            spec_matches.append(value); spans.append(_span(text,match.start(),match.end(),"specialization",value))
    specialization=spec_matches[0] if len(spec_matches)==1 else None
    grade_matches=[]
    for grade,pattern in [("intern",r"\bintern\b|\btrainee\b|стаж[её]р"),("junior",r"\bjunior\b|джуниор"),("middle",r"\bmiddle\b|\bmid\b|мидл"),("senior",r"\bsenior\b|сеньор")]:
        match=re.search(pattern,text,re.I)
        if match:
            grade_matches.append(grade); spans.append(_span(text,match.start(),match.end(),"grade",grade))
    grade=grade_matches[0] if len(grade_matches)==1 else None
    salary_from=salary_to=None
    # A range must carry explicit RUB marker; foreign currency is not converted.
    salary=re.search(r"(?P<lo>\d{2,6}(?:[ \u00a0]\d{3})?)\s*(?P<unit>тыс\.?|[kк])?\s*(?:[-–—]|до)\s*(?P<hi>\d{2,6}(?:[ \u00a0]\d{3})?)\s*(?P<unit2>тыс\.?|[kк])?\s*(?:руб\.?|₽|RUB)",text,re.I)
    if salary:
        lo=int(re.sub(r"\s","",salary.group("lo"))); hi=int(re.sub(r"\s","",salary.group("hi")))
        if salary.group("unit") or salary.group("unit2"):
            if lo<1000: lo*=1000
            if hi<1000: hi*=1000
        if lo<=hi:
            salary_from,salary_to=lo,hi; spans.append(_span(text,salary.start(),salary.end(),"salary",{"from":lo,"to":hi}))
    work_format=None
    for value,pattern in [("remote",r"удал[её]н\w*|\bremote\b"),("hybrid",r"гибрид\w*|\bhybrid\b"),("office",r"в\s+офисе|офисный\s+формат|\bon.?site\b")]:
        match=re.search(pattern,text,re.I)
        if match:
            if work_format is not None and value!=work_format: work_format=None; break
            work_format=value; spans.append(_span(text,match.start(),match.end(),"work_format",value))
    warnings=["Результат — черновик. Подтвердите требования, грейд и условия перед сохранением."]
    if conflicts: warnings.append("Противоречивые упоминания: "+", ".join(conflicts))
    if len(spec_matches)>1: warnings.append("Упомянуто несколько направлений; требуется выбор.")
    if len(grade_matches)>1: warnings.append("Упомянуто несколько грейдов; требуется выбор или диапазон.")
    return {"specialization":specialization,"grade":grade,"skills":skills,"required_skills":required,"preferred_skills":preferred,"excluded_skills":excluded,"salary_from":salary_from,"salary_to":salary_to,"work_format":work_format,"employment":None,"source_spans":sorted(spans,key=lambda row:row["start"]),"spans":sorted(spans,key=lambda row:row["start"]),"conflicts":conflicts,"warnings":warnings,"requires_confirmation":True,"extraction_version":EXTRACTION_VERSION,"semantic_model":"rules_baseline"}
