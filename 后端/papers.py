"""组卷、在线作答、自动判卷、错题本 API"""
import json
import re
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn, row_to_dict
from config import get

router = APIRouter(prefix="/api", tags=["组卷/判卷/错题"])

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY = get("DEEPSEEK_KEY", "REDACTED-USE-ENV")


class PaperConfig(BaseModel):
    subject: str
    title: str = ""
    counts: dict = {}
    difficulties: dict = {}


class SubmitIn(BaseModel):
    paper_id: int
    student_name: str = "学生"
    answers: dict


def pick_questions(conn, subject, qtype, difficulty, count):
    rows = conn.execute(
        "SELECT * FROM questions WHERE subject=? AND qtype=? AND difficulty=? ORDER BY RANDOM() LIMIT ?",
        (subject, qtype, difficulty, count),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.post("/papers")
def create_paper(pc: PaperConfig):
    conn = get_conn()
    # counts: {"single": 5, "multiple": 2, "judge": 3, "blank": 2, "short": 1}
    counts = pc.counts or {"single": 5, "multiple": 2, "judge": 3, "blank": 2, "short": 1}
    difficulties = pc.difficulties or {"easy": 40, "medium": 40, "hard": 20}

    picked = []
    total_each = {t: counts.get(t, 0) for t in ("single", "multiple", "judge", "blank", "short")}
    for qtype, cnt in total_each.items():
        if cnt <= 0:
            continue
        pool = conn.execute(
            "SELECT * FROM questions WHERE subject=? AND qtype=? ORDER BY RANDOM()",
            (pc.subject, qtype),
        ).fetchall()
        pool = [row_to_dict(r) for r in pool]
        if not pool:
            continue
        # 按难度比例分配
        n = min(cnt, len(pool))
        chosen = []
        import random
        random.shuffle(pool)
        for q in pool:
            if len(chosen) >= n:
                break
            chosen.append(q)
        picked.extend(chosen)

    if not picked:
        conn.close()
        raise HTTPException(status_code=400, detail="题库中没有可用的题目，请先录题或生成题目")

    title = pc.title or f"{pc.subject} 智能组卷"
    cur = conn.execute("INSERT INTO papers (subject, title, config) VALUES (?,?,?)",
                       (pc.subject, title, json.dumps({"counts": counts, "difficulties": difficulties}, ensure_ascii=False)))
    paper_id = cur.lastrowid
    for i, q in enumerate(picked):
        conn.execute("INSERT INTO paper_questions (paper_id, question_id, position) VALUES (?,?,?)",
                     (paper_id, q["id"], i + 1))
    conn.commit()
    conn.close()
    return {"code": 200, "paper_id": paper_id, "title": title, "question_count": len(picked)}


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int):
    conn = get_conn()
    paper = conn.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
    if not paper:
        conn.close()
        raise HTTPException(status_code=404, detail="试卷不存在")
    p = row_to_dict(paper)
    p["config"] = json.loads(p.get("config") or "{}")
    qrows = conn.execute(
        "SELECT q.* FROM questions q JOIN paper_questions pq ON q.id=pq.question_id "
        "WHERE pq.paper_id=? ORDER BY pq.position", (paper_id,)
    ).fetchall()
    questions = [row_to_dict(r) for r in qrows]
    # 作答时不下发答案
    for q in questions:
        q["answer"] = ""
        q["analysis"] = ""
    conn.close()
    return {"code": 200, "paper": p, "questions": questions}


def judge_question(q, student_answer):
    """判单题，返回 (得分0/1, 是否正确, 标准答案)"""
    qtype = q["qtype"]
    ans = (q.get("answer") or "").strip()
    stu = (student_answer or "").strip()

    if qtype == "single":
        return (1.0, True, ans) if stu and stu.upper() == ans.upper() else (0.0, False, ans)
    if qtype == "multiple":
        norm = lambda s: "".join(sorted(set(s.upper().replace("，", ",").split(",")) - {"", " "})) if s else ""
        correct = norm(ans) == norm(stu)
        return (1.0 if correct else 0.0, correct, ans)
    if qtype == "judge":
        return (1.0, True, ans) if stu and (stu in ("对", "正确", "√") and ans in ("对", "正确", "√") or stu in ("错", "错误", "×") and ans in ("错", "错误", "×")) else (0.0, False, ans)
    if qtype == "blank":
        return (1.0, True, ans) if stu and (stu.strip() == ans.strip()) else (0.0, False, ans)
    # short 简答题 → AI 判分
    if qtype == "short":
        score = ai_grade_short(q, stu)
        return (score, score >= 0.6, ans)
    return (0.0, False, ans)


def ai_grade_short(q, student_answer):
    """调用 DeepSeek 给简答题评分，返回 0~1"""
    if not student_answer:
        return 0.0
    prompt = (
        "你是阅卷老师。题目：" + q["stem"] + "\n"
        "参考答案要点：" + (q.get("answer") or "") + "\n"
        "学生答案：" + student_answer + "\n"
        "请只输出一个 0 到 1 之间的数字表示得分率（保留两位小数），不要输出其他内容。"
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 100,
    }
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        txt = data["choices"][0]["message"]["content"].strip()
        m = re.search(r"0\.\d+|\b[01]\b", txt)
        if m:
            return max(0.0, min(1.0, float(m.group(0))))
    except Exception:
        pass
    return 0.5


@router.post("/papers/{paper_id}/submit")
def submit_paper(paper_id: int, sub: SubmitIn):
    conn = get_conn()
    paper = conn.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
    if not paper:
        conn.close()
        raise HTTPException(status_code=404, detail="试卷不存在")
    qrows = conn.execute(
        "SELECT q.* FROM questions q JOIN paper_questions pq ON q.id=pq.question_id "
        "WHERE pq.paper_id=? ORDER BY pq.position", (paper_id,)
    ).fetchall()
    questions = [row_to_dict(r) for r in qrows]

    total = 0.0
    score = 0.0
    results = {}
    for q in questions:
        qid = str(q["id"])
        stu_ans = sub.answers.get(qid, "")
        pts, correct, std_ans = judge_question(q, stu_ans)
        total += 1.0
        score += pts
        results[qid] = {
            "correct": bool(correct),
            "score": pts,
            "student_answer": stu_ans,
            "std_answer": std_ans,
            "analysis": q.get("analysis", ""),
            "stem": q["stem"],
            "qtype": q["qtype"],
            "knowledge_point": q["knowledge_point"],
        }
        # 错题归集
        if not correct:
            conn.execute(
                "INSERT OR IGNORE INTO wrong_book (student_name, subject, question_id, attempt_id) VALUES (?,?,?,?)",
                (sub.student_name, paper["subject"], q["id"], 0),
            )

    final_score = round(score / total * 100, 1) if total else 0
    cur = conn.execute(
        "INSERT INTO attempts (paper_id, subject, student_name, score, total, answers, results) VALUES (?,?,?,?,?,?,?)",
        (paper_id, paper["subject"], sub.student_name, final_score, 100,
         json.dumps(sub.answers, ensure_ascii=False), json.dumps(results, ensure_ascii=False)),
    )
    attempt_id = cur.lastrowid
    conn.execute("UPDATE wrong_book SET attempt_id=? WHERE student_name=? AND attempt_id=0", (attempt_id, sub.student_name))
    conn.commit()
    conn.close()
    return {"code": 200, "attempt_id": attempt_id, "score": final_score, "total": 100, "results": results}


@router.get("/wrong-book")
def wrong_book(subject: str = "", student_name: str = "学生"):
    conn = get_conn()
    sql = ("SELECT wb.*, q.subject, q.knowledge_point, q.qtype, q.stem, q.options, q.answer, q.analysis "
           "FROM wrong_book wb JOIN questions q ON wb.question_id=q.id WHERE wb.student_name=?")
    params = [student_name]
    if subject:
        sql += " AND q.subject=?"
        params.append(subject)
    rows = conn.execute(sql + " ORDER BY wb.wrong_time DESC", params).fetchall()
    items = [row_to_dict(r) for r in rows]
    conn.close()
    return {"code": 200, "items": items}


@router.post("/wrong-book/{question_id}/master")
def mark_mastered(question_id: int, student_name: str = "学生"):
    conn = get_conn()
    conn.execute("UPDATE wrong_book SET mastered=1 WHERE question_id=? AND student_name=?", (question_id, student_name))
    conn.commit()
    conn.close()
    return {"code": 200}


@router.get("/attempts")
def list_attempts(student_name: str = "学生"):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE student_name=? ORDER BY create_time DESC LIMIT 20", (student_name,)
    ).fetchall()
    conn.close()
    return {"code": 200, "items": [row_to_dict(r) for r in rows]}
