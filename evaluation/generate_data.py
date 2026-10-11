"""Regenerate explicit original fixtures/author ledger. Never modifies a database."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services"/"api"))
from app.engines.bank import CHOICES,family_manifest
from app.engines.scenarios import SCENARIOS
from app.engines.seed import demo_seed,generate_population,generate_needs


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return {"path":str(path.relative_to(ROOT)).replace("\\","/"),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--population",type=int,default=0);args=parser.parse_args()
    ledger={row[0]:row[2] for entries in CHOICES.values() for row in entries}
    ledger.update({row[0]:row[2] for grades in SCENARIOS.values() for entries in grades.values() for row in entries})
    files=[write(ROOT/"assessment-bank"/"manifest.json",family_manifest()),write(ROOT/"assessment-bank"/"author-review-ledger.json",ledger),write(ROOT/"data"/"demo-seed.json",demo_seed()),write(ROOT/"data"/"synthetic-needs-v1.json",generate_needs())]
    if args.population:
        files.append(write(ROOT/"data"/"synthetic-candidates-v1.json",generate_population(args.population)))
    write(ROOT/"data"/"dataset-manifest.json",{"version":"vector-data-v1","origin":"PROJECT_ORIGINAL_SYNTHETIC","human_records":0,"real_fsp_records":0,"files":files,"limitation":"Author-ledger choice keys are not independent human semantic review. Programmatic simulation does not calibrate real grades or hiring."})
    print(json.dumps({"families":len(family_manifest()),"files":files},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
