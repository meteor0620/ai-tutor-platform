"""知识库访问 API：浏览、检索（代理 MaxKB，不暴露内部凭据）"""
import json
import urllib.request

from fastapi import APIRouter
from pydantic import BaseModel

from config import get

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])

MAXKB_BASE = get("MAXKB_BASE", "http://localhost:8080")
MAXKB_ADMIN = get("MAXKB_ADMIN", "admin")
MAXKB_PASSWORD = get("MAXKB_PASSWORD", "")  # 从 .env 读取, 勿硬编码

# 科目 -> MaxKB 知识库 ID
KNOWLEDGE_MAP = {
    "math": "01a06c99-7356-7a33-bbde-951f91a48ee6",
    "english": "01a06c99-73fd-7ef1-aa4b-b4ae09dde458",
}

_admin_token_cache = {"token": None}


def get_admin_token() -> str:
    if _admin_token_cache["token"]:
        return _admin_token_cache["token"]
    payload = json.dumps({
        "username": MAXKB_ADMIN, "password": MAXKB_PASSWORD, "current_role": "ADMIN"
    }).encode("utf-8")
    req = urllib.request.Request(MAXKB_BASE + "/admin/api/user/login", data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    token = data["data"]["token"]
    _admin_token_cache["token"] = token
    return token


def maxkb_post(path: str, body: dict, timeout: int = 60):
    token = get_admin_token()
    req = urllib.request.Request(MAXKB_BASE + path, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def maxkb_get(path: str, timeout: int = 60):
    token = get_admin_token()
    req = urllib.request.Request(MAXKB_BASE + path, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class SearchIn(BaseModel):
    subject: str
    query: str
    top_n: int = 5
    search_mode: str = "blend"


@router.get("/{subject}/documents")
def list_documents(subject: str):
    kb_id = KNOWLEDGE_MAP.get(subject)
    if not kb_id:
        return {"code": 400, "message": "未知科目"}
    data = maxkb_get(f"/admin/api/workspace/default/knowledge/{kb_id}/document")
    docs = []
    for d in data.get("data", []):
        docs.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "paragraph_count": d.get("paragraph_count", 0),
            "status": d.get("status"),
        })
    return {"code": 200, "items": docs}


@router.get("/{subject}/documents/{document_id}/sections")
def list_sections(subject: str, document_id: str, page: int = 1, page_size: int = 50):
    kb_id = KNOWLEDGE_MAP.get(subject)
    if not kb_id:
        return {"code": 400, "message": "未知科目"}
    data = maxkb_get(
        f"/admin/api/workspace/default/knowledge/{kb_id}/document/{document_id}/paragraph/{page}/{page_size}"
    )
    sections = []
    for p in data.get("data", []).get("records", []) if isinstance(data.get("data"), dict) else []:
        sections.append({
            "id": p.get("id"),
            "title": p.get("title", ""),
            "content": p.get("content", ""),
        })
    total = data.get("data", {}).get("total", 0) if isinstance(data.get("data"), dict) else 0
    return {"code": 200, "total": total, "items": sections}


@router.post("/{subject}/search")
def search_knowledge(subject: str, s: SearchIn):
    kb_id = KNOWLEDGE_MAP.get(subject)
    if not kb_id:
        return {"code": 400, "message": "未知科目"}
    data = maxkb_post(f"/admin/api/workspace/default/knowledge/{kb_id}/hit_test", {
        "query_text": s.query,
        "top_number": s.top_n,
        "similarity": 0.1,
        "search_mode": s.search_mode,
    })
    results = []
    for p in data.get("data", []):
        results.append({
            "title": p.get("title", ""),
            "content": p.get("content", ""),
            "similarity": round(p.get("similarity", 0), 3),
            "document_name": p.get("document_name", ""),
        })
    return {"code": 200, "query": s.query, "items": results}
