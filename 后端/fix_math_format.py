# -*- coding: utf-8 -*-
r"""
数学知识库格式修复：
1. 「高等数学微积分完整笔记」：从 LaTeX 源 md 重新转换（修复旧版转换器
   \in/\int、\le/\left、\cdot/\cdots、\leq/\leqslant 替换顺序 bug 产生的
   ∈t / ≤ft( / ≤slant / ·s 等残迹），重新分段 + 标题注入
2. 「高等数学讲义」「高等数学下册讲义」：段落内容就地 LaTeX 清洗（此前从未清洗过）
三个文档均删除重建，等向量化完成后才进行下一个。
运行：PYTHONIOENCODING=utf-8 python fix_math_format.py（不要自行包装 stdout，
replace_math_doc 导入时已包装，双重包装会触发 I/O operation on closed file）
"""
import sys
import time

import requests

from config import get
from replace_math_doc import SRC, MAX_CHARS, clean_text, chunk_md

BASE = get("MAXKB_BASE", "http://localhost:8080").rstrip("/")
ids = __import__("json").load(open("rebuild_ids.json", encoding="utf-8"))
KB = ids["math_kb"]

NOTES_DOC = "高等数学微积分完整笔记"
LECTURE_DOCS = ["高等数学讲义", "高等数学下册讲义"]

s = requests.Session()
r = s.post(BASE + "/admin/api/user/login",
           json={"username": get("MAXKB_ADMIN", "admin"), "password": get("MAXKB_PASSWORD", ""),
                 "current_role": "ADMIN"}, timeout=30)
s.headers["Authorization"] = "Bearer " + r.json()["data"]["token"]


def list_paragraphs(doc_id):
    out, page = [], 1
    while True:
        d = s.get(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document/{doc_id}/paragraph/{page}/200",
                  timeout=60).json()["data"]
        records = d.get("records", []) if isinstance(d, dict) else []
        out += records
        if page * 200 >= d.get("total", 0) or not records:
            return out
        page += 1


def find_doc(name):
    docs = s.get(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document",
                 params={"page_size": 100}, timeout=30).json()["data"]
    hit = [d for d in docs if d["name"] == name]
    return hit[0] if hit else None


def rebuild(name, paragraphs):
    """删除同名旧文档 -> batch_create -> 等向量化完成"""
    old = find_doc(name)
    if old:
        r = s.delete(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document/{old['id']}", timeout=60)
        print(f"[{name}] 删除旧文档 {old['id']}: code={r.json().get('code')}", flush=True)
        time.sleep(3)
    payload = [{"name": name,
                "paragraphs": [{"title": t, "content": c, "is_active": True} for t, c in paragraphs]}]
    r = s.put(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document/batch_create",
              json=payload, timeout=300)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"[{name}] batch_create 失败: {str(j)[:400]}")
    new_id = j["data"][0]["id"]
    print(f"[{name}] 已创建 {new_id}, {len(paragraphs)} 段, 等待向量化...", flush=True)
    for _ in range(60):
        time.sleep(15)
        d = find_doc(name)
        st, pc = str(d["status"]), d.get("paragraph_count", 0)
        print(f"  [{name}] status={st} paragraphs={pc}/{len(paragraphs)}", flush=True)
        if st.endswith("2") and pc == len(paragraphs):
            print(f"[{name}] 向量化完成 ✓", flush=True)
            return
    raise RuntimeError(f"[{name}] 向量化超时")


# ---------- 1. 微积分完整笔记：源 md 重转 ----------
md = open(SRC, encoding="utf-8").read()
print(f"源文件 {len(md)} 字符")
clean = clean_text(md)
paras = chunk_md(clean)
merged = [(t, (f"【{t}】\n{c}" if t else c)) for t, c in paras]
avg = len(clean) // max(len(merged), 1)
print(f"清洗后 {len(clean)} 字符 -> {len(merged)} 段 (平均 {avg} 字/段)")
rebuild(NOTES_DOC, merged)

# ---------- 2. 两份讲义：就地清洗 ----------
for name in LECTURE_DOCS:
    doc = find_doc(name)
    if not doc:
        print(f"[{name}] 文档不存在，跳过")
        continue
    paras = list_paragraphs(doc["id"])
    new, changed = [], 0
    for p in paras:
        title = (p.get("title") or "").strip()
        content = p.get("content") or ""
        fixed = clean_text(content)
        if fixed != content:
            changed += 1
        new.append((title, fixed))
    print(f"[{name}] {len(new)} 段中 {changed} 段有改动")
    rebuild(name, new)

print("全部完成 ✓")
