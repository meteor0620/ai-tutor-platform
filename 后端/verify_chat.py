# -*- coding: utf-8 -*-
"""端到端验证 AI 答疑：anonymous -> open -> chat_message（走 MaxKB 真实链路）"""
import io
import json
import sys

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from config import get

BASE = get("MAXKB_BASE", "http://localhost:8080").rstrip("/")
ids = json.load(open("rebuild_ids.json", encoding="utf-8"))

CASES = [
    ("数学", ids["math_app_token"], "什么是洛必达法则？使用条件是什么？"),
    ("英语", ids["english_app_token"], "四级写作常用的连接词有哪些？"),
]

for subject, token, q in CASES:
    r = requests.post(BASE + "/chat/api/auth/anonymous",
                      json={"access_token": token}, timeout=30)
    token_chat = r.json()["data"]
    chat_id = requests.get(BASE + "/chat/api/open",
                           headers={"Authorization": "Bearer " + token_chat}, timeout=30).json()["data"]
    r = requests.post(BASE + f"/chat/api/chat_message/{chat_id}",
                      json={"message": q, "stream": False, "re_chat": False},
                      headers={"Authorization": "Bearer " + token_chat}, timeout=120)
    content = r.json()["data"]["content"]
    print(f"===== {subject}: {q}")
    print(content[:500].replace("\n", " ")[:500])
    print(f"[回复长度 {len(content)} 字]\n")
