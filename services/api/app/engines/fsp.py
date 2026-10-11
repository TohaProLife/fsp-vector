"""Explicit demonstration registry identity/provenance. No invented official API."""

import hmac
from copy import deepcopy
from datetime import datetime,timezone

DEMO_SOURCE="FSP_DEMO_CONFIRMED"


def demo_link(fsp_id:str,proof_code:str,email:str,records:list|None=None) -> dict:
    if records is None:
        from .seed import demo_seed
        records=demo_seed()["fsp_records"]
    record=next((row for row in records if hmac.compare_digest(str(row.get("fsp_id","")),str(fsp_id))),None)
    if not record or str(record.get("email","")).casefold()!=str(email).casefold() or not hmac.compare_digest(str(record.get("proof_code","")),str(proof_code)):
        raise ValueError("Демо-ID или подтверждение владения не совпадает с текущим аккаунтом.")
    achievements=deepcopy(record.get("achievements",[]))
    for achievement in achievements:
        achievement["source"]=DEMO_SOURCE
        achievement["status"]="active" if not achievement.get("revoked") else "revoked"
    return {"fsp_id":record["fsp_id"],"status":"sync_ok" if achievements else "linked_no_history","source":DEMO_SOURCE,"achievements":achievements,"synced_at":datetime.now(timezone.utc).isoformat(),"is_demo":True,"notice":"Синтетический локальный реестр. Это не официальное подтверждение ФСП."}


def unlink_projection() -> dict:
    return {"fsp_id":None,"status":"not_linked","source":None,"achievements":[],"is_demo":False}
