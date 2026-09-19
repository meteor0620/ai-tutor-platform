"""知识库访问 API：浏览、检索（代理 MaxKB，不暴露内部凭据）"""
import json
import logging
import os
import urllib.error
import urllib.request

from fastapi import APIRouter
from pydantic import BaseModel

from config import get

log = logging.getLogger("knowledge")

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])

MAXKB_BASE = get("MAXKB_BASE", "http://localhost:8080")
MAXKB_ADMIN = get("MAXKB_ADMIN", "admin")
MAXKB_PASSWORD = get("MAXKB_PASSWORD", "")  # 从 .env 读取, 勿硬编码

# 科目 -> MaxKB 知识库 ID（单一事实源：rebuild_ids.json，重建库后只改那里）
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rebuild_ids.json"), encoding="utf-8") as _f:
    _IDS = json.load(_f)
KNOWLEDGE_MAP = {"math": _IDS["math_kb"], "english": _IDS["english_kb"]}

_admin_token_cache = {"token": None}


def _login() -> str:
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


def get_admin_token(force: bool = False) -> str:
    if not force and _admin_token_cache["token"]:
        return _admin_token_cache["token"]
    return _login()


class MaxKBError(Exception):
    """MaxKB 侧错误，携带用户可读信息"""


def _request(method: str, path: str, body: dict | None = None, timeout: int = 60):
    """带 401 自动重登重试一次的 MaxKB 请求"""
    for attempt in (1, 2):
        token = get_admin_token(force=(attempt == 2))
        req = urllib.request.Request(MAXKB_BASE + path, method=method)
        if body is not None:
            req.data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                log.warning("MaxKB admin token 过期，自动重登重试")
                continue
            raise MaxKBError(f"MaxKB 返回 {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise MaxKBError(f"MaxKB 不可达: {e.reason}") from e


def maxkb_post(path: str, body: dict, timeout: int = 60):
    return _request("POST", path, body, timeout)


def maxkb_get(path: str, timeout: int = 60):
    return _request("GET", path, None, timeout)


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
    try:
        data = maxkb_get(f"/admin/api/workspace/default/knowledge/{kb_id}/document")
    except MaxKBError as e:
        log.error("documents 接口失败: %s", e)
        return {"code": 502, "message": f"知识库服务暂时不可用：{e}"}
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
    try:
        data = maxkb_get(
            f"/admin/api/workspace/default/knowledge/{kb_id}/document/{document_id}/paragraph/{page}/{page_size}"
        )
    except MaxKBError as e:
        log.error("sections 接口失败: %s", e)
        return {"code": 502, "message": f"知识库服务暂时不可用：{e}"}
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
    try:
        data = maxkb_post(f"/admin/api/workspace/default/knowledge/{kb_id}/hit_test", {
            "query_text": s.query,
            "top_number": s.top_n,
            "similarity": 0.1,
            "search_mode": s.search_mode,
        })
    except MaxKBError as e:
        log.error("search 接口失败: %s", e)
        return {"code": 502, "message": f"知识库服务暂时不可用：{e}"}
    results = []
    for p in data.get("data", []):
        results.append({
            "title": p.get("title", ""),
            "content": p.get("content", ""),
            "similarity": round(p.get("similarity", 0), 3),
            "document_name": p.get("document_name", ""),
        })
    return {"code": 200, "query": s.query, "items": results}
