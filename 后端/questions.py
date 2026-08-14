"""题库 API：手动录入、查询、AI 批量生成"""
import json
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn, row_to_dict
from config import get

router = APIRouter(prefix="/api/questions", tags=["题库"])

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY = get("DEEPSEEK_KEY", "")  # 从 .env 读取, 勿硬编码


class QuestionIn(BaseModel):
    subject: str
    knowledge_point: str
    qtype: str
    difficulty: str = "medium"
    stem: str
    options: list = []
    answer: str
    analysis: str = ""
    source: str = "manual"


class QuestionList(BaseModel):
    subject: str = ""
    knowledge_point: str = ""
    qtype: str = ""
    page: int = 1
    size: int = 50


class GenerateIn(BaseModel):
    subject: str
    knowledge_point: str
    qtype: str = "single"
    count: int = 5
    difficulty: str = "medium"


@router.get("")
def list_questions(subject: str = "", knowledge_point: str = "", qtype: str = "", page: int = 1, size: int = 50):
    conn = get_conn()
    sql = "SELECT * FROM questions WHERE 1=1"
    params = []
    if subject:
        sql += " AND subject = ?"
        params.append(subject)
    if knowledge_point:
        sql += " AND knowledge_point LIKE ?"
        params.append(f"%{knowledge_point}%")
    if qtype:
        sql += " AND qtype = ?"
        params.append(qtype)
    total = conn.execute(sql.replace("SELECT *", "SELECT COUNT(*)"), params).fetchone()[0]
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [size, (page - 1) * size]
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {"total": total, "items": [row_to_dict(r) for r in rows]}


@router.post("")
def create_question(q: QuestionIn):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO questions (subject, knowledge_point, qtype, difficulty, stem, options, answer, analysis, source) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (q.subject, q.knowledge_point, q.qtype, q.difficulty, q.stem, json.dumps(q.options, ensure_ascii=False),
         q.answer, q.analysis, q.source),
    )
    conn.commit()
    qid = cur.lastrowid
    conn.close()
    return {"code": 200, "data": {"id": qid}}


@router.put("/{qid}")
def update_question(qid: int, q: QuestionIn):
    """更新题目（教师端题库管理·编辑）"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM questions WHERE id=?", (qid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="题目不存在")
    conn.execute(
        "UPDATE questions SET subject=?, knowledge_point=?, qtype=?, difficulty=?, stem=?, options=?, "
        "answer=?, analysis=? WHERE id=?",
        (q.subject, q.knowledge_point, q.qtype, q.difficulty, q.stem,
         json.dumps(q.options, ensure_ascii=False), q.answer, q.analysis, qid),
    )
    conn.commit()
    conn.close()
    return {"code": 200, "data": {"id": qid}}


@router.delete("/{qid}")
def delete_question(qid: int):
    conn = get_conn()
    conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
    conn.commit()
    conn.close()
    return {"code": 200}


@router.get("/stats")
def question_stats(subject: str = ""):
    """题库数量分布：{科目: {题型: 数量, 'total': 总数}}（教师端题库页统计卡）"""
    conn = get_conn()
    sql = "SELECT subject, qtype, count(*) c FROM questions WHERE 1=1"
    params = []
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    sql += " GROUP BY subject, qtype"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    from collections import defaultdict
    stats = defaultdict(lambda: {"total": 0})
    for r in rows:
        s = stats[r["subject"]]
        s[r["qtype"]] = r["c"]
        s["total"] += r["c"]
    return {"code": 200, "items": dict(stats)}


def call_deepseek(prompt: str, temperature: float = 0.7) -> str:
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 8192,
    }
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_generated(raw: str):
    """解析 AI 生成的题目 JSON（可能带 markdown 围栏）"""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("[")
    end = raw.rfind("]")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


@router.post("/generate")
def generate_questions(g: GenerateIn):
    type_names = {
        "single": "单选题（含4个选项，选项A/B/C/D，答案填选项字母）",
        "multiple": "多选题（含4-5个选项，答案填选项字母组合）",
        "judge": "判断题（答案填对/错）",
        "blank": "填空题（答案填文本）",
        "short": "简答题（答案填参考要点）",
    }
    prompt = (
        f"你是{('高等数学' if g.subject == 'math' else '大学英语')}的出题老师，请围绕知识点"
        f"「{g.knowledge_point}」生成 {g.count} 道{g.qtype}题。\n"
        f"题型要求：{type_names.get(g.qtype, g.qtype)}\n"
        f"必须输出严格的 JSON 数组，不要输出任何其他内容，格式如下：\n"
        f'[{{"stem":"题干","options":["A. xxx","B. xxx","C. xxx","D. xxx"],"answer":"正确选项","analysis":"解析","difficulty":"easy|medium|hard"}}]\n'
        f"注意：判断题 options 传空数组，填空题 options 传空数组，简答题 options 传空数组。"
    )
    raw = call_deepseek(prompt)
    try:
        items = parse_generated(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 返回格式解析失败: {e}\n{raw[:500]}")
    if not isinstance(items, list):
        raise HTTPException(status_code=500, detail="AI 返回不是数组")

    conn = get_conn()
    created = 0
    for it in items:
        stem = it.get("stem", "")
        answer = it.get("answer", "")
        if not stem or not answer:
            continue
        difficulty = it.get("difficulty", g.difficulty)
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        conn.execute(
            "INSERT INTO questions (subject, knowledge_point, qtype, difficulty, stem, options, answer, analysis, source) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (g.subject, g.knowledge_point, g.qtype, difficulty, stem,
             json.dumps(it.get("options", []), ensure_ascii=False), answer, it.get("analysis", ""), "ai"),
        )
        created += 1
    conn.commit()
    conn.close()
    return {"code": 200, "created": created}
