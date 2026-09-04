# -*- coding: utf-8 -*-
"""
MaxKB 空库重建 第一步：创建 DeepSeek LLM 模型 + 两个知识库
幂等：已存在的按名字复用。结果写入 rebuild_ids.json 供后续步骤使用。
"""
import io
import json
import sys

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from config import get

BASE = get("MAXKB_BASE", "http://localhost:8080").rstrip("/")
ADMIN = get("MAXKB_ADMIN", "admin")
PASSWORD = get("MAXKB_PASSWORD", "")
EMBEDDING_ID = "42f63a3d-427e-11ef-b3ec-a8a1595801ab"  # 内置 maxkb-embedding（已查实）
IDS_FILE = "rebuild_ids.json"

KB_SPECS = [
    {"name": "高等数学", "desc": "高等数学知识库：微积分完整笔记（4章136节）+ 高等数学讲义"},
    {"name": "大学英语", "desc": "大学英语知识库：大学英语讲义 + 四级真题（28套）"},
]


def login():
    s = requests.Session()
    r = s.post(BASE + "/admin/api/user/login",
               json={"username": ADMIN, "password": PASSWORD, "current_role": "ADMIN"}, timeout=30)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"登录失败: {j.get('message')}")
    s.headers["Authorization"] = "Bearer " + j["data"]["token"]
    return s


def ensure_deepseek_model(s):
    models = s.get(BASE + "/admin/api/workspace/default/model", timeout=30).json()["data"]
    llm = [m for m in models if m["model_type"] == "LLM"]
    if llm:
        print(f"LLM 模型已存在: {llm[0]['name']} ({llm[0]['model_name']}) -> {llm[0]['id']}")
        return llm[0]["id"]
    key = get("DEEPSEEK_KEY", "")
    if not key:
        raise RuntimeError("需要创建 LLM 模型但 .env 无 DEEPSEEK_KEY")
    r = s.post(BASE + "/admin/api/workspace/default/model", json={
        "name": "DeepSeek",
        "provider": "model_deepseek_provider",
        "model_type": "LLM",
        "model_name": "deepseek-v4-flash",
        "credential": {"api_base": "https://api.deepseek.com", "api_key": key},
    }, timeout=120)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"创建 DeepSeek 模型失败: {j.get('message')} {r.text[:300]}")
    model_id = j["data"]["id"]
    print(f"LLM 模型已创建: DeepSeek (deepseek-v4-flash) -> {model_id}")
    return model_id


def ensure_knowledge(s, spec):
    kbs = s.get(BASE + "/admin/api/workspace/default/knowledge", params={"page_size": 100}, timeout=30).json()["data"]
    for kb in (kbs if isinstance(kbs, list) else kbs.get("records", [])):
        if kb["name"] == spec["name"]:
            print(f"知识库已存在: {kb['name']} -> {kb['id']}")
            return kb["id"]
    r = s.post(BASE + "/admin/api/workspace/default/knowledge/base", json={
        "name": spec["name"], "desc": spec["desc"], "embedding_model_id": EMBEDDING_ID,
        "folder_id": "default",
    }, timeout=60)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"创建知识库 {spec['name']} 失败: {j.get('message')} {r.text[:300]}")
    kb_id = j["data"]["id"]
    print(f"知识库已创建: {spec['name']} -> {kb_id}")
    return kb_id


def main():
    s = login()
    print("登录 OK")
    model_id = ensure_deepseek_model(s)
    kb_ids = {spec["name"]: ensure_knowledge(s, spec) for spec in KB_SPECS}
    out = {"model_id": model_id, "math_kb": kb_ids["高等数学"], "english_kb": kb_ids["大学英语"]}
    with open(IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("已写入", IDS_FILE, json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
