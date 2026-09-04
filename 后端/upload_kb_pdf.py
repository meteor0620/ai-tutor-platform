# -*- coding: utf-8 -*-
"""
MaxKB 知识库批量上传工具（2026-08-08 验证可用）

用途: 把本地文件夹里的 PDF 上传到指定 MaxKB 知识库。
要点(踩坑记录):
  1. 扫描件(无文本层)直接传会变成 0 段落死档 —— 上传前用 PyMuPDF 检测文本层, 自动跳过。
  2. split 返回的 content 段列表必须转成 paragraphs 再提交 batch_create,
     直接传 content 字段会被 DRF 静默忽略(只建空壳文档)。
  3. 并发/大文档可能压垮 Postgres(recovery mode)导致全体 401, 故串行+低并发+401自动重登。
  4. hit_test 参数是 query_text/top_number/similarity/search_mode, 不是 question。

用法:
  python upload_kb_pdf.py --dir "英语四级" --kb 019fd0cc-250f-72e3-b6f1-fab9d66278d6 \
      --username admin --password 'xxx' --base http://localhost:8080
"""
import argparse
import io
import json
import os
import sys
import time

import fitz
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def has_text_layer(pdf: str, min_ok_pages: int = 3) -> bool:
    """检测 PDF 是否有足够文本层(>=min_ok_pages 页有>20字), 否则判定为扫描件"""
    try:
        doc = fitz.open(pdf)
        pages = doc.page_count
        ok = sum(1 for i in range(pages) if len(doc[i].get_text().strip()) > 20)
        doc.close()
        return ok >= max(min_ok_pages, pages // 2)
    except Exception:
        return False


def login(s: requests.Session, base: str, username: str, password: str):
    r = s.post(base + "/admin/api/user/login",
               json={"username": username, "password": password, "current_role": "ADMIN"}, timeout=30)
    s.headers["Authorization"] = "Bearer " + r.json()["data"]["token"]


def upload_pdf(s: requests.Session, base: str, kb_id: str, pdf: str, label: str,
               username: str, password: str):
    """split -> 转 paragraphs -> batch_create, 401 自动重登重试 3 次"""
    name = label
    for attempt in range(3):
        try:
            with open(pdf, "rb") as f:
                r = s.post(base + f"/admin/api/workspace/default/knowledge/{kb_id}/document/split",
                           files={"file": (os.path.basename(pdf), f, "application/pdf")},
                           data={"with_filter": "true"}, timeout=300)
            if r.status_code == 401 or (r.json().get("code") == 1002):
                login(s, base, username, password)
                time.sleep(2)
                continue
            docs = r.json().get("data") or []
            if not docs:
                return (name, "EMPTY", "split 返回空")
            d = docs[0]
            segs = d.get("content") or []
            paragraphs = [{"title": seg.get("title", "") or "", "content": seg.get("content", ""), "is_active": True}
                          for seg in segs if seg.get("content")]
            if not paragraphs:
                return (name, "EMPTY", "无有效内容段(疑似扫描件)")
            payload = [{"name": d.get("name"), "source_file_id": d.get("source_file_id"),
                        "paragraphs": paragraphs}]
            r2 = s.put(base + f"/admin/api/workspace/default/knowledge/{kb_id}/document/batch_create",
                       json=payload, timeout=300)
            j2 = r2.json()
            if r2.status_code == 401 or j2.get("code") == 1002:
                login(s, base, username, password)
                time.sleep(2)
                continue
            if j2.get("code") != 200:
                return (name, "ERROR", str(j2.get("message"))[:120])
            data2 = j2.get("data")
            pid = data2[0].get("id") if isinstance(data2, list) and data2 else "?"
            return (name, "OK", f"{len(paragraphs)}段 {pid}")
        except Exception as e:
            time.sleep(3)
    return (name, "FAIL", "重试3次仍失败")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="要上传的文件夹(递归找PDF)")
    ap.add_argument("--kb", required=True, help="知识库ID")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--min-ok-pages", type=int, default=3, help="文本层达标页数阈值(扫描件判定)")
    ap.add_argument("--exclude", default="", help="文件相对路径命中该正则则跳过(如 '解析|答案速查')")
    args = ap.parse_args()

    s = requests.Session()
    login(s, args.base, args.username, args.password)

    if not os.path.isdir(args.dir):
        print(f"目录不存在: {args.dir}")
        return
    import re
    excl = re.compile(args.exclude) if args.exclude else None
    pdfs = [os.path.join(r_, f) for r_, d, fs in os.walk(args.dir)
            for f in fs if f.lower().endswith(".pdf")]
    print(f"共 {len(pdfs)} 个PDF, 检测文本层中...")
    todo, skipped = [], []
    for p in pdfs:
        rel = os.path.relpath(p, args.dir)
        if excl and excl.search(rel.replace("\\", "/")):
            skipped.append(p)
            print("  [跳过-排除]", rel)
            continue
        if has_text_layer(p, args.min_ok_pages):
            todo.append(p)
        else:
            skipped.append(p)
    for p in skipped:
        print("  [跳过-扫描件]", os.path.relpath(p, args.dir))
    print(f"将上传 {len(todo)} 个, 串行执行(避免压垮数据库)...\n")

    results = []
    for i, p in enumerate(todo, 1):
        name, status, msg = upload_pdf(s, args.base, args.kb, p, os.path.relpath(p, args.dir),
                                       args.username, args.password)
        results.append((name, status, msg))
        print(f"  [{i}/{len(todo)}] [{status}] {name}  {msg}", flush=True)
        time.sleep(1.5)

    ok = [r_ for r_ in results if r_[1] == "OK"]
    print(f"\n完成: OK {len(ok)} / {len(todo)}")
    for r_ in results:
        if r_[1] != "OK":
            print("  ", r_[0], "->", r_[1], r_[2])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "upload_kb_result.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("结果已存:", out)


if __name__ == "__main__":
    main()
