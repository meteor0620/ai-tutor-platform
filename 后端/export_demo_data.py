# -*- coding: utf-8 -*-
"""
导出 GitHub Pages 演示版静态数据：
1. 题库 SQLite -> public/demo/questions_{math|english}.json
2. MaxKB 知识库段落 -> public/demo/kb_{math|english}.json（含文档树）
输出到 门户/public/demo/，前端 demo 模式直接 fetch 使用。
"""
import io
import json
import sqlite3
import sys

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"E:\AI教辅智学平台\meteor-master\meteor-master\后端")
from config import get

OUT = r"E:\AI教辅智学平台\meteor-master\meteor-master\门户\public\demo"
ids = json.load(open(r"E:\AI教辅智学平台\meteor-master\meteor-master\后端\rebuild_ids.json", encoding="utf-8"))

# ---------- 1. 题库 ----------
con = sqlite3.connect(r"E:\AI教辅智学平台\meteor-master\meteor-master\后端\aiplatform.db")
con.row_factory = sqlite3.Row
cols = [r[1] for r in con.execute("PRAGMA table_info(questions)")]
print("questions 列:", cols)
rows = [dict(r) for r in con.execute("SELECT * FROM questions")]
print("总题数:", len(rows))

# 按科目分组
by_sub = {"math": [], "english": []}
for r in rows:
    sub = r.get("subject") or ("math" if r.get("course") == "math" else None)
    if sub is None and "course" in r:
        sub = r["course"]
    if sub not in by_sub:
        sub = "math"
    by_sub[sub].append(r)

import os
os.makedirs(OUT, exist_ok=True)
for sub, items in by_sub.items():
    with open(f"{OUT}/questions_{sub}.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    print(f"questions_{sub}.json: {len(items)} 题")

# ---------- 2. 知识库段落 ----------
s = requests.Session()
r = s.post(get("MAXKB_BASE", "http://localhost:8080") + "/admin/api/user/login",
           json={"username": get("MAXKB_ADMIN", "admin"), "password": get("MAXKB_PASSWORD", ""),
                 "current_role": "ADMIN"}, timeout=30)
s.headers["Authorization"] = "Bearer " + r.json()["data"]["token"]

for sub, kb in (("math", ids["math_kb"]), ("english", ids["english_kb"])):
    docs = s.get(get("MAXKB_BASE", "http://localhost:8080") + f"/admin/api/workspace/default/knowledge/{kb}/document",
                 params={"page_size": 100}, timeout=30).json()["data"]
    docs_out = []
    for d in docs:
        paras = []
        page = 1
        while True:
            pd = s.get(get("MAXKB_BASE", "http://localhost:8080") +
                       f"/admin/api/workspace/default/knowledge/{kb}/document/{d['id']}/paragraph/{page}/200",
                       timeout=60).json()["data"]
            recs = pd.get("records", []) if isinstance(pd, dict) else []
            paras += [{"title": p.get("title", ""), "content": p.get("content", "")} for p in recs]
            if page * 200 >= pd.get("total", 0) or not recs:
                break
            page += 1
        docs_out.append({"name": d["name"], "paragraphs": paras})
        print(f"  [{sub}] {d['name']}: {len(paras)} 段")
    with open(f"{OUT}/kb_{sub}.json", "w", encoding="utf-8") as f:
        json.dump(docs_out, f, ensure_ascii=False)
    print(f"kb_{sub}.json 完成: {len(docs_out)} 文档")
print("导出完成 ->", OUT)
