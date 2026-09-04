# -*- coding: utf-8 -*-
"""标题前缀注入：把段落标题并入正文后重建文档，提升向量+关键词信号"""
import io
import json
import sys
import time

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

TARGETS = [(ids["math_kb"], "高等数学微积分完整笔记"), (ids["english_kb"], "大学英语讲义")]


def list_paragraphs(kb, doc):
    out, page = [], 1
    while True:
        d = s.get(BASE + f"/admin/api/workspace/default/knowledge/{kb}/document/{doc}/paragraph/{page}/200",
                  timeout=60).json()["data"]
        records = d.get("records", []) if isinstance(d, dict) else []
        out += records
        if page * 200 >= d.get("total", 0) or not records:
            return out
        page += 1


for kb, name in TARGETS:
    docs = s.get(BASE + f"/admin/api/workspace/default/knowledge/{kb}/document",
                 params={"page_size": 100}, timeout=30).json()["data"]
    doc = [d for d in docs if d["name"] == name][0]
    paras = list_paragraphs(kb, doc["id"])
    new = []
    for p in paras:
        title, content = (p.get("title") or "").strip(), p.get("content") or ""
        if title and not content.lstrip().startswith("【"):
            content = f"【{title}】\n{content}"
        new.append({"title": title, "content": content, "is_active": True})
    r = s.delete(BASE + f"/admin/api/workspace/default/knowledge/{kb}/document/{doc['id']}", timeout=60)
    print(f"[{name}] 删除旧文档 {r.json().get('code')}, 重建 {len(new)} 段(标题已并入正文)")
    time.sleep(3)
    payload = [{"name": name, "paragraphs": new}]
    r = s.put(BASE + f"/admin/api/workspace/default/knowledge/{kb}/document/batch_create",
              json=payload, timeout=300)
    if r.json().get("code") != 200:
        raise RuntimeError(f"batch_create 失败 {name}: {str(r.json())[:300]}")
    new_id = r.json()["data"][0]["id"]
    for _ in range(40):
        time.sleep(15)
        docs = s.get(BASE + f"/admin/api/workspace/default/knowledge/{kb}/document",
                     params={"page_size": 100}, timeout=30).json()["data"]
        d = [x for x in docs if x["id"] == new_id][0]
        st, pc = str(d["status"]), d.get("paragraph_count", 0)
        print(f"  [{name}] status={st} paragraphs={pc}/{len(new)}", flush=True)
        if st.endswith("2") and pc == len(new):
            print(f"  [{name}] 向量化完成")
            break
