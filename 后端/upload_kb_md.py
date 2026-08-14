# -*- coding: utf-8 -*-
"""
把本地 markdown 文件上传到指定 MaxKB 知识库(2026-08-09 验证可用)

流程与 upload_kb_pdf.py 相同: split -> 转 paragraphs -> batch_create。
区别: 目标文件是 .md(mime text/markdown), 凭据从 后端/.env 读取(config.py)。
用法:
  python upload_kb_md.py --file ../素材/高等数学下册讲义.md \
      --kb 019fd0cc-24a8-7fe2-a148-b1a44f6bfe4c --name "高等数学下册讲义"
"""
import argparse
import io
import json
import os
import sys
import time

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from config import get

BASE = get("MAXKB_BASE", "http://localhost:8081").rstrip("/")
ADMIN = get("MAXKB_ADMIN", "admin")
PASSWORD = get("MAXKB_PASSWORD", "")


def login(s: requests.Session):
    r = s.post(BASE + "/admin/api/user/login",
               json={"username": ADMIN, "password": PASSWORD, "current_role": "ADMIN"}, timeout=30)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"登录失败: {j.get('message')} (检查 .env 的 MAXKB_ADMIN/MAXKB_PASSWORD)")
    s.headers["Authorization"] = "Bearer " + j["data"]["token"]


def upload_md(s: requests.Session, kb_id: str, md_path: str, name: str):
    with open(md_path, "rb") as f:
        r = s.post(BASE + f"/admin/api/workspace/default/knowledge/{kb_id}/document/split",
                   files={"file": (os.path.basename(md_path), f, "text/markdown")},
                   data={"with_filter": "true"}, timeout=300)
    j = r.json()
    if j.get("code") != 200:
        return ("FAIL", str(j.get("message"))[:150])
    docs = j.get("data") or []
    if not docs:
        return ("FAIL", "split 返回空")
    d = docs[0]
    segs = d.get("content") or []
    paragraphs = [{"title": seg.get("title", "") or "", "content": seg.get("content", ""), "is_active": True}
                  for seg in segs if seg.get("content")]
    if not paragraphs:
        return ("FAIL", "无有效内容段")
    payload = [{"name": name or d.get("name"), "source_file_id": d.get("source_file_id"),
                "paragraphs": paragraphs}]
    r2 = s.put(BASE + f"/admin/api/workspace/default/knowledge/{kb_id}/document/batch_create",
               json=payload, timeout=300)
    j2 = r2.json()
    if j2.get("code") != 200:
        return ("FAIL", str(j2.get("message"))[:150])
    return ("OK", f"{len(paragraphs)}段")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--kb", required=True)
    ap.add_argument("--name", default="")
    args = ap.parse_args()

    s = requests.Session()
    login(s)

    status, msg = upload_md(s, args.kb, args.file, args.name)
    print(f"[{status}] {args.file} -> {msg}")
    if status != "OK":
        sys.exit(1)


if __name__ == "__main__":
    main()
