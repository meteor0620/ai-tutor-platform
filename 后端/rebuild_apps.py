# -*- coding: utf-8 -*-
"""
MaxKB 重建 第二步：创建两个 SIMPLE 应用(按 _app_math/_app_english 蓝本)、绑定知识库、publish、取 access_token
幂等：按应用名复用已存在的应用。结果追加进 rebuild_ids.json。
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
IDS_FILE = "rebuild_ids.json"

SYSTEM_PROMPT = "你是高校课程AI助教，回答要精炼、结构化、准确。"
NO_REF = "知识库没有相关内容时请明确说明，不要编造。"
NO_REF_PROMPT = "知识库中没有相关内容时请明确说明，不要编造。"
OPT_PROMPT = "优化用户的问题，使其更清晰完整，便于知识库检索。"

APPS = [
    {
        "key": "math_app",
        "name": "AI微积分助教",
        "desc": "高等数学AI答疑助教（RAG）",
        "kb_field": "math_kb",
        "prompt": ("请回答用户的问题：{question}\n"
                   "请根据下面的知识库内容回答问题，只使用与问题最匹配的<data>段落，忽略无关段落。\n"
                   "回答结构：① 核心思想 ② 公式 ③ 必考点 ④ 易错点 ⑤ 几何直观（如适用）。\n"
                   "如果知识库没有相关内容，直接说明。\n<data>\n{data}\n</data>"),
    },
    {
        "key": "english_app",
        "name": "AI英语助教",
        "desc": "大学英语AI答疑助教（RAG）",
        "kb_field": "english_kb",
        "prompt": ("请回答用户的问题：{question}\n"
                   "请根据下面的知识库内容回答问题，只使用与问题最匹配的<data>段落，忽略无关段落。\n"
                   "回答结构：① 核心要点 ② 词汇/语法/用法 ③ 常见错误 ④ 例句。\n"
                   "如果知识库没有相关内容，直接说明。\n<data>\n{data}\n</data>"),
    },
]


def login():
    s = requests.Session()
    r = s.post(BASE + "/admin/api/user/login",
               json={"username": ADMIN, "password": PASSWORD, "current_role": "ADMIN"}, timeout=30)
    s.headers["Authorization"] = "Bearer " + r.json()["data"]["token"]
    return s


def app_payload(spec, kb_id, model_id):
    return {
        "name": spec["name"], "desc": spec["desc"], "prologue": "",
        "dialogue_number": 8, "folder_id": "default",
        "model_id": model_id, "knowledge_id_list": [kb_id],
        "knowledge_setting": {
            "top_n": 5, "similarity": 0.3, "search_mode": "blend",
            "no_references_setting": {"value": NO_REF, "status": "ai_questioning"},
            "max_paragraph_char_number": 6000,
        },
        "model_setting": {
            "prompt": spec["prompt"], "system": SYSTEM_PROMPT,
            "no_references_prompt": NO_REF_PROMPT, "reasoning_content_enable": False,
        },
        "model_params_setting": {"temperature": 0.4},
        "problem_optimization": False, "problem_optimization_prompt": OPT_PROMPT,
        "type": "SIMPLE", "icon": "./favicon.ico",
        "tts_model_enable": False, "tts_type": "BROWSER", "tts_autoplay": False,
        "stt_model_enable": False, "stt_autosend": False,
        "file_upload_enable": False, "file_upload_setting": {},
        "mcp_enable": False, "tool_enable": False, "application_enable": False,
    }


def ensure_app(s, spec, kb_id, model_id):
    apps = s.get(BASE + "/admin/api/workspace/default/application",
                 params={"page_size": 100, "ordering": "-create_time"}, timeout=30).json()["data"]
    for a in (apps if isinstance(apps, list) else apps.get("records", [])):
        if a["name"] == spec["name"]:
            print(f"应用已存在: {a['name']} -> {a['id']}")
            return a["id"]
    r = s.post(BASE + "/admin/api/workspace/default/application",
               json=app_payload(spec, kb_id, model_id), timeout=60)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"创建应用 {spec['name']} 失败: {j.get('message')} {r.text[:400]}")
    app_id = j["data"]["id"]
    print(f"应用已创建: {spec['name']} -> {app_id}")
    return app_id


def ensure_publish(s, app_id):
    detail = s.get(BASE + f"/admin/api/workspace/default/application/{app_id}", timeout=30).json()["data"]
    if detail.get("is_publish") and detail.get("knowledge_id_list"):
        print(f"  已发布，跳过 publish")
        return
    # PUT 校正配置（必带 knowledge_id_list）
    put = {k: detail[k] for k in ("name", "desc", "prologue", "dialogue_number", "knowledge_setting",
                                  "model_setting", "model_params_setting", "problem_optimization",
                                  "problem_optimization_prompt", "icon", "type")}
    put["model_id"] = detail.get("model_id") or detail.get("model")
    put["knowledge_id_list"] = detail.get("knowledge_id_list") or []
    put["tts_model_enable"] = detail.get("tts_model_enable", False)
    put["stt_model_enable"] = detail.get("stt_model_enable", False)
    r = s.put(BASE + f"/admin/api/workspace/default/application/{app_id}", json=put, timeout=60)
    if r.json().get("code") != 200:
        raise RuntimeError(f"PUT 应用失败: {r.text[:300]}")
    r = s.put(BASE + f"/admin/api/workspace/default/application/{app_id}/publish", json={}, timeout=60)
    if r.json().get("code") != 200:
        raise RuntimeError(f"publish 失败: {r.text[:300]}")
    print("  已重新 PUT + publish")


def ensure_token(s, app_id):
    tok = s.get(BASE + f"/admin/api/workspace/default/application/{app_id}/access_token", timeout=30).json()["data"]
    if not tok.get("is_active"):
        r = s.put(BASE + f"/admin/api/workspace/default/application/{app_id}/access_token",
                  json={"is_active": True}, timeout=30)
        tok = r.json()["data"]
    return tok["access_token"]


def main():
    ids = json.load(open(IDS_FILE, encoding="utf-8"))
    s = login()
    print("登录 OK")
    for spec in APPS:
        kb_id = ids[spec["kb_field"]]
        app_id = ensure_app(s, spec, kb_id, ids["model_id"])
        ensure_publish(s, app_id)
        token = ensure_token(s, app_id)
        ids[spec["key"]] = app_id
        ids[spec["key"] + "_token"] = token
        print(f"  access_token: {token}")
    json.dump(ids, open(IDS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n最终 ID:", json.dumps(ids, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
