# -*- coding: utf-8 -*-
"""调优：top_n 10 / similarity 0.15 / max_paragraph_char_number 20000，PUT + publish"""
import io
import json
import sys

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from config import get

BASE = get("MAXKB_BASE", "http://localhost:8080").rstrip("/")
ids = json.load(open("rebuild_ids.json", encoding="utf-8"))

s = requests.Session()
r = s.post(BASE + "/admin/api/user/login",
           json={"username": get("MAXKB_ADMIN", "admin"), "password": get("MAXKB_PASSWORD", ""),
                 "current_role": "ADMIN"}, timeout=30)
s.headers["Authorization"] = "Bearer " + r.json()["data"]["token"]

for app_key in ("math_app", "english_app"):
    app_id = ids[app_key]
    d = s.get(BASE + f"/admin/api/workspace/default/application/{app_id}", timeout=30).json()["data"]
    d["knowledge_setting"]["top_n"] = 12
    d["knowledge_setting"]["similarity"] = 0.15
    d["knowledge_setting"]["max_paragraph_char_number"] = 60000
    put = {k: d[k] for k in ("name", "desc", "prologue", "dialogue_number", "knowledge_setting",
                             "model_setting", "model_params_setting", "problem_optimization",
                             "problem_optimization_prompt", "icon", "type")}
    put["model_id"] = d.get("model_id") or d.get("model")
    put["knowledge_id_list"] = d.get("knowledge_id_list") or []
    r = s.put(BASE + f"/admin/api/workspace/default/application/{app_id}", json=put, timeout=60)
    if r.json().get("code") != 200:
        raise RuntimeError(f"PUT 失败 {app_key}: {r.text[:300]}")
    r = s.put(BASE + f"/admin/api/workspace/default/application/{app_id}/publish", json={}, timeout=60)
    if r.json().get("code") != 200:
        raise RuntimeError(f"publish 失败 {app_key}: {r.text[:300]}")
    print(f"{app_key}: top_n=10 sim=0.15 已发布")
