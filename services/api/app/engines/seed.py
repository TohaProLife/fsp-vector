"""Original deterministic synthetic data, never a record of real achievements."""

import random
from datetime import datetime,timedelta,timezone
from .taxonomy import COMPETENCY_SKILLS,GRADES,SPECIALIZATIONS

DATASET_VERSION="vector-synthetic-v1"
REFERENCE_DATE=datetime(2026,10,7,9,0,tzinfo=timezone.utc)
FIRST_NAMES=["Алексей","Мария","Илья","Дарья","Артём","Анна","Михаил","Полина","Денис","София","Никита","Елена","Сергей","Алина","Олег","Вера"]
LAST_NAMES=["Соколов","Орлова","Миронов","Волкова","Лебедев","Лазарева","Кузнецов","Романова","Егоров","Белова","Фёдоров","Новикова","Белов","Зайцева","Громов","Иванова"]
CITIES=["Москва","Санкт-Петербург","Казань","Новосибирск","Екатеринбург","Томск","Самара","Пермь"]
STACKS={"backend":["Python","FastAPI","PostgreSQL","Redis","SQL","API"],"frontend":["TypeScript","React","JavaScript","Доступность","Playwright"],"qa":["Test design","API","SQL","pytest","Playwright"],"devops":["Linux","Docker","Kubernetes","Prometheus","SLO","Terraform"],"data":["SQL","PostgreSQL","pandas","Статистика","Data quality"],"security":["OWASP","Authorization","Cryptography","CTF","Incident response"]}
TASK_CONTEXTS={"backend":["платёжного API","платформы обработки событий","системы каталогов","сервиса командной работы"],"frontend":["доступного кабинета","редактора рабочих процессов","аналитического интерфейса","продуктовой дизайн-системы"],"qa":["проверки финансовых операций","автоматизации API тестов","релизного процесса","матрицы доступов"],"devops":["наблюдаемости платформы","безопасных релизов","конфигурации сервисов","восстановления после сбоев"],"data":["проверки метрик продукта","качества событий","когортного анализа","витрины отчётности"],"security":["аудита авторизации","безопасного дизайна API","реагирования на инциденты","анализа учебных web-сценариев"]}


def _achievement(index,spec,rng):
    participants=rng.randrange(20,150)
    return {"event_id":f"DEMO-EVENT-{index:04d}","title":f"Демонстрационный кубок {index%9+1}","discipline":"CTF" if spec=="security" else "Алгоритмическое программирование","specializations":[spec] if spec in ("backend","data","qa","security") else [],"level":"regional" if index%3 else "national","date":(REFERENCE_DATE-timedelta(days=rng.randrange(10,600))).date().isoformat(),"place":rng.randrange(1,participants+1),"participants":participants,"team":index%4==0,"role":None if index%4==0 else "individual","score":rng.randrange(30,100),"protocol_id":f"DEMO-PROTOCOL-{index:04d}","protocol_url":None,"source":"FSP_DEMO_CONFIRMED","status":"active","is_demo":True}


def generate_population(count=3000,seed=20261007,include_latent=False):
    rng=random.Random(seed); candidates=[]
    for index in range(count):
        spec=list(SPECIALIZATIONS)[index%6]; grade=GRADES[(index//6)%4]
        skills=list(STACKS[spec]); rng.shuffle(skills)
        mastered={skill:rng.uniform(.45,1.) for skill in sorted(set(skill for comp in SPECIALIZATIONS[spec]["competencies"] for skill in COMPETENCY_SKILLS[comp]))}
        observed={skill:max(0.,min(1.,value+rng.uniform(-.18,.18))) for skill,value in mastered.items()}
        score=round(rng.uniform(70,100),2)
        when=REFERENCE_DATE-timedelta(days=rng.randrange(0,180))
        evidence=[{"skill":skill,"source":"ASSESSMENT_VERIFIED","status":"verified","strength":round(value,3),"score":round(value*100,2),"confirmed_at":when.isoformat(),"scope":{"specialization":spec,"grade":grade,"mode":"synthetic_fixture"},"origin":"SYNTHETIC_SEED","is_demo":True} for skill,value in observed.items() if rng.random()>.15]
        name=FIRST_NAMES[index%16]+" "+LAST_NAMES[index%16]
        salary=40_000+GRADES.index(grade)*60_000+rng.randrange(0,6)*10_000
        work_format=rng.choice(["remote","remote","hybrid","office"])
        fsp={"status":"not_linked","source":None,"achievements":[]}
        if index%3==0:
            fsp={"fsp_id":f"FSP-DEMO-{index+1:03d}","status":"sync_ok","source":"FSP_DEMO_CONFIRMED","achievements":[_achievement(index,spec,rng)],"is_demo":True}
        candidate={"id":f"synthetic-{index+1:04d}","email":f"persona-{index+1:04d}@vector.local","name":name,"alias":f"Вектор {index+1:03d}","title":f"{SPECIALIZATIONS[spec]['label']} · {grade.capitalize()}","bio":f"Вымышленный профиль для проверки {TASK_CONTEXTS[spec][index%4]}. Интересуюсь ясными контрактами, измеримыми результатами и командной работой.","city":CITIES[index%8],"specialization":spec,"declared_grade":grade,"confirmed_grade":grade,"score":score,"skills":skills,"preferences":{"salary_from":salary,"salary_to":salary+80_000,"work_format":work_format,"employment":"full_time","strict_salary":True,"strict_work_format":True},"published":index%17!=0,"active":True,"evidence":evidence,"assessment_at":when.isoformat(),"fsp":fsp,"origin":"SYNTHETIC_SEED","is_demo":True,"category_source":"SYNTHETIC_SEED","calibration_status":"synthetic_fixture","limitations":"Подробный вымышленный профиль. Никакой реальный человек не проходил этот экзамен."}
        if include_latent:
            candidate["_latent"]={"specialization":spec,"grade":grade,"mastery":mastered,"salary_min":salary,"work_format":work_format}
        candidates.append(candidate)
    return candidates


def generate_needs(count=150,seed=20261008):
    rng=random.Random(seed); needs=[]
    for index in range(count):
        spec=list(SPECIALIZATIONS)[index%6]; grade=GRADES[(index//6)%4]
        verified=list(dict.fromkeys(skill for comp in SPECIALIZATIONS[spec]["competencies"] for skill in COMPETENCY_SKILLS[comp]))
        required=rng.sample(verified,min(2,len(verified)))
        preferred=rng.sample(STACKS[spec],min(2,len(STACKS[spec])))
        salary=60_000+GRADES.index(grade)*70_000
        format=rng.choice(["remote","remote","hybrid","office"])
        description=f"Команда {TASK_CONTEXTS[spec][index%4]} ищет {grade.capitalize()} {SPECIALIZATIONS[spec]['label']}. Обязательные проверяемые темы: {', '.join(required)}. Желательны {', '.join(preferred)}. Работа {'удалённо' if format=='remote' else 'гибридно' if format=='hybrid' else 'в офисе'}. Зарплата {salary}–{salary+100_000} RUB. Потребность и компания вымышлены."
        needs.append({"id":f"need-fixture-{index+1:03d}","title":f"{SPECIALIZATIONS[spec]['label']} для {TASK_CONTEXTS[spec][index%4]}","description":description,"specialization":spec,"grade":grade,"skills":preferred,"required_skills":required,"salary_from":salary,"salary_to":salary+100_000,"work_format":format,"employment":"full_time","team":"Продуктовая команда · 6 человек","require_verified_skills":True,"must_have_mode":"verified","origin":"SYNTHETIC_SEED","is_demo":True})
    return needs


def _challenge(index,spec):
    from .assessment import create_form,public_form
    form=create_form(spec,"junior",seed=9910+index)
    private=next(item for item in form["items"] if item["slot"]=="practice")
    public=next(item for item in public_form(form)["items"] if item["id"]==private["id"])
    return {"id":f"challenge-fixture-{index+1}","title":private["title"],"description":"Короткая практика по синтетическим данным. Результат не меняет подтверждённый грейд.","specialization":spec,"skill":COMPETENCY_SKILLS[private["competency"]][0],"public_task":public,"private_rubric":private,"origin":"SYNTHETIC_SEED","is_demo":True}


def demo_seed():
    candidates=generate_population(48)
    current=candidates[0]
    current.update({"email":"candidate@vector.local","name":"Алексей Вектор","alias":"Алексей Вектор","title":"Backend-разработчик","confirmed_grade":None,"score":None,"evidence":[],"published":False,"assessment_at":None,"fsp":{"status":"not_linked","source":None,"achievements":[]},"declared_grade":"middle","specialization":"backend","preferences":{"salary_from":150000,"salary_to":240000,"work_format":"remote","employment":"full_time"},"skills":["Python","FastAPI","PostgreSQL","SQL","API"],"bio":"Демонстрационный аккаунт для полного пути: профиль → опрос → настоящий экзамен → публикация → предложение. Все персональные данные вымышлены."})
    # Profiles illustrating meaningful domain and privacy states.
    candidates[1].update({"alias":"Сильный профиль без ФСП","score":96,"fsp":{"status":"not_linked","source":None,"achievements":[]}})
    candidates[6]["fsp"]["status"]="sync_stale"
    candidates[9]["fsp"]["achievements"][0]["status"]="revoked"
    candidates[12]["preferences"]["salary_from"]=500_000
    candidates[18]["published"]=False
    # A curated, explicit demo match: a synthetic Backend/Middle profile with
    # no FSP bonus, observed SQL/API and remote preferences. No live account is
    # silently given this result.
    strong=candidates[36]
    strong.update({"alias":"Сильный Backend без ФСП","score":94,"published":True,"fsp":{"status":"not_linked","source":None,"achievements":[]},"preferences":{"salary_from":160000,"salary_to":260000,"work_format":"remote","employment":"full_time"},"evidence":[{"skill":skill,"source":"ASSESSMENT_VERIFIED","status":"verified","strength":.94,"score":94,"confirmed_at":REFERENCE_DATE.isoformat(),"scope":{"specialization":"backend","grade":"middle","mode":"synthetic_fixture"},"origin":"SYNTHETIC_SEED","is_demo":True} for skill in ("SQL","API","HTTP","Идемпотентность","Unit testing")]})
    rng=random.Random(5050)
    fsp_records=[]
    for index in range(500):
        spec=list(SPECIALIZATIONS)[index%6]
        fsp_records.append({"fsp_id":f"FSP-DEMO-{index+1:03d}","email":"candidate@vector.local" if index==0 else f"persona-{index+1:04d}@vector.local","proof_code":"VECTOR-2026" if index==0 else f"DEMO-{index+1:04d}","achievements":[] if index%11==10 else [_achievement(index,spec,rng)],"source":"FSP_DEMO_CONFIRMED","is_demo":True})
    needs=generate_needs()
    needs[0].update({"title":"Backend для платформы событий","description":"Ищем Middle Backend в команду платформы событий. Обязательны подтверждённые SQL и API; Python и FastAPI желательны. Удалённая работа, 180000–280000 RUB. Все сведения и компания демонстрационные.","specialization":"backend","grade":"middle","skills":["Python","FastAPI","SQL","API"],"required_skills":["SQL","API"],"salary_from":180000,"salary_to":280000,"work_format":"remote"})
    return {"metadata":{"dataset_id":DATASET_VERSION,"generated_at":REFERENCE_DATE.isoformat(),"seed":20261007,"origin":"SYNTHETIC_SEED","license":"Project-original synthetic content","human_participants":0,"limitation":"Синтетические данные не доказывают качество реального найма или калибровку грейдов."},"candidates":candidates,"needs":needs,"fsp_records":fsp_records,"challenges":[_challenge(index,spec) for index,spec in enumerate(SPECIALIZATIONS)]}
