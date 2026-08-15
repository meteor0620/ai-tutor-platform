"""组卷、在线作答、自动判卷、错题本 API"""
import json
import random
import re
import urllib.request
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn, row_to_dict
from config import get

router = APIRouter(prefix="/api", tags=["组卷/判卷/错题"])

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY = get("DEEPSEEK_KEY", "")  # 从 .env 读取, 勿硬编码


class PaperConfig(BaseModel):
    subject: str
    title: str = ""
    counts: dict = {}
    difficulties: dict = {}
    passages: int = 0  # 英语阅读按文章组卷: 抽几篇文章(每篇5题) + 1道翻译
    knowledge_points: dict = {}  # 英语自主选题型组卷: {"阅读": 篇数, "翻译": 题数, "词汇": 题数, ...}
    source: str = "auto"  # auto=学生随机组卷 / teacher=教师指定卷


class SubmitIn(BaseModel):
    paper_id: int
    student_name: str = "学生"
    answers: dict


class ReviewIn(BaseModel):
    """错题重练：基于未掌握错题的知识点重新组卷"""
    student_name: str
    subject: str = ""


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

    # 英语按题型自主组卷: knowledge_points = {"阅读": 篇数, "翻译": 题数, ...}
    if pc.subject == "english" and pc.knowledge_points:
        import random
        picked = []
        for kp, cnt in pc.knowledge_points.items():
            if cnt <= 0:
                continue
            if kp == "阅读":
                keys = [r[0] for r in conn.execute(
                    "SELECT DISTINCT passage_key FROM questions "
                    "WHERE subject='english' AND passage_key != '' ORDER BY RANDOM()").fetchall()]
                for k in random.sample(keys, min(cnt, len(keys))):
                    rows = conn.execute(
                        "SELECT * FROM questions WHERE subject='english' AND passage_key=? "
                        "ORDER BY id", (k,)).fetchall()
                    picked.extend([row_to_dict(r) for r in rows])
            elif kp == "翻译":
                rows = conn.execute(
                    "SELECT * FROM questions WHERE subject='english' AND knowledge_point='翻译' "
                    "AND qtype='short' ORDER BY RANDOM() LIMIT ?", (cnt,)).fetchall()
                picked.extend([row_to_dict(r) for r in rows])
            else:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE subject='english' AND knowledge_point=? "
                    "ORDER BY RANDOM() LIMIT ?", (kp, cnt)).fetchall()
                picked.extend([row_to_dict(r) for r in rows])
        # 按 id 去重保持顺序
        seen, ordered = set(), []
        for q in picked:
            if q["id"] not in seen:
                seen.add(q["id"])
                ordered.append(q)
        picked = ordered
        if not picked:
            conn.close()
            raise HTTPException(status_code=400, detail="所选题型暂无可用题目，请重新选择")
        parts = [f"{kp}×{cnt}{'篇' if kp == '阅读' else '题'}"
                 for kp, cnt in pc.knowledge_points.items() if cnt > 0]
        title = pc.title or ("英语四级 · " + "+".join(parts))
        cur = conn.execute("INSERT INTO papers (subject, title, config, source) VALUES (?,?,?,?)",
                           (pc.subject, title, json.dumps({"counts": counts, "difficulties": difficulties,
                                                          "knowledge_points": pc.knowledge_points}, ensure_ascii=False),
                            pc.source))
        paper_id = cur.lastrowid
        for i, q in enumerate(picked):
            conn.execute("INSERT INTO paper_questions (paper_id, question_id, position) VALUES (?,?,?)",
                         (paper_id, q["id"], i + 1))
        conn.commit()
        conn.close()
        return {"code": 200, "paper_id": paper_id, "title": title, "question_count": len(picked)}

    # 英语阅读按文章组卷: 随机抽 N 篇文章(每篇5题) + 1道翻译简答
    if pc.passages > 0 and pc.subject == "english":
        import random
        keys = [r[0] for r in conn.execute(
            "SELECT DISTINCT passage_key FROM questions "
            "WHERE subject='english' AND passage_key != '' ORDER BY RANDOM()").fetchall()]
        if keys:
            n = min(pc.passages, len(keys))
            chosen = random.sample(keys, n)
            picked = []
            for k in chosen:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE subject='english' AND passage_key=? "
                    "ORDER BY passage_key, id", (k,)).fetchall()
                picked.extend([row_to_dict(r) for r in rows])
            # 补一道翻译
            tro = conn.execute(
                "SELECT * FROM questions WHERE subject='english' AND qtype='short' "
                "AND knowledge_point='翻译' ORDER BY RANDOM() LIMIT 1").fetchone()
            if tro:
                picked.append(row_to_dict(tro))
        else:
            picked = []

        if not picked:
            conn.close()
            raise HTTPException(status_code=400, detail="英语题库暂无可用题目，请先导入真题")
        title = pc.title or f"英语四级 · 真题自测（{n}篇阅读+翻译）"
        cur = conn.execute("INSERT INTO papers (subject, title, config, source) VALUES (?,?,?,?)",
                           (pc.subject, title, json.dumps({"counts": counts, "difficulties": difficulties,
                                                          "passages": pc.passages}, ensure_ascii=False),
                            pc.source))
        paper_id = cur.lastrowid
        for i, q in enumerate(picked):
            conn.execute("INSERT INTO paper_questions (paper_id, question_id, position) VALUES (?,?,?)",
                         (paper_id, q["id"], i + 1))
        conn.commit()
        conn.close()
        return {"code": 200, "paper_id": paper_id, "title": title, "question_count": len(picked)}

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
        # 按难度配比抽题（difficulties: {"easy":40,"medium":40,"hard":20}）
        n = min(cnt, len(pool))
        by_diff = defaultdict(list)
        for q in pool:
            d = q.get("difficulty") or "medium"
            if d not in ("easy", "medium", "hard"):
                d = "medium"
            by_diff[d].append(q)
        chosen = _pick_by_difficulty(n, difficulties, by_diff, pool)
        picked.extend(chosen)

    if not picked:
        conn.close()
        raise HTTPException(status_code=400, detail="题库中没有可用的题目，请先录题或生成题目")

    title = pc.title or f"{pc.subject} 智能组卷"
    cur = conn.execute("INSERT INTO papers (subject, title, config, source) VALUES (?,?,?,?)",
                       (pc.subject, title, json.dumps({"counts": counts, "difficulties": difficulties}, ensure_ascii=False),
                        pc.source))
    paper_id = cur.lastrowid
    for i, q in enumerate(picked):
        conn.execute("INSERT INTO paper_questions (paper_id, question_id, position) VALUES (?,?,?)",
                     (paper_id, q["id"], i + 1))
    conn.commit()
    conn.close()
    return {"code": 200, "paper_id": paper_id, "title": title, "question_count": len(picked)}


@router.post("/papers/review")
def create_review_paper(rv: ReviewIn):
    """错题强化闭环：按该生未掌握错题的知识点重新组卷，做错的题优先不出（换同知识点新题）"""
    import random
    conn = get_conn()
    # 1. 该生该科目未掌握错题的知识点集合（去重）
    kp_sql = ("SELECT q.knowledge_point, count(*) c FROM wrong_book wb "
              "JOIN questions q ON wb.question_id=q.id "
              "WHERE wb.student_name=? AND wb.mastered=0")
    params = [rv.student_name]
    if rv.subject:
        kp_sql += " AND q.subject=?"
        params.append(rv.subject)
    kp_rows = conn.execute(kp_sql + " GROUP BY q.knowledge_point ORDER BY c DESC LIMIT 5", params).fetchall()
    kps = [(r["knowledge_point"], r["c"]) for r in kp_rows]
    if not kps:
        conn.close()
        raise HTTPException(status_code=400, detail="当前没有待巩固的薄弱点")

    # 该生已做过的题（排除，优先换新题）
    done_ids = {r[0] for r in conn.execute(
        "SELECT question_id FROM wrong_book WHERE student_name=?", (rv.student_name,)).fetchall()}

    picked = []
    for kp, cnt in kps:
        n = min(cnt, 3)  # 每知识点最多 3 道
        # 优先该知识点下没做错过的题
        rows = conn.execute(
            "SELECT * FROM questions WHERE knowledge_point=? ORDER BY RANDOM() LIMIT 200",
            (kp,)).fetchall()
        fresh = [row_to_dict(r) for r in rows if r["id"] not in done_ids]
        rest = [row_to_dict(r) for r in rows if r["id"] in done_ids]
        random.shuffle(fresh)
        random.shuffle(rest)
        chosen = (fresh + rest)[:n]
        picked.extend(chosen)

    if not picked:
        conn.close()
        raise HTTPException(status_code=400, detail="题库暂无薄弱点相关题目，请老师补充")
    # 按 id 去重保持顺序
    seen, ordered = set(), []
    for q in picked:
        if q["id"] not in seen:
            seen.add(q["id"])
            ordered.append(q)
    picked = ordered
    if not picked:
        conn.close()
        raise HTTPException(status_code=400, detail="当前暂无薄弱点可巩固")

    title = f"{rv.student_name} · 薄弱点巩固"
    cur = conn.execute("INSERT INTO papers (subject, title, config, source) VALUES (?,?,?,?)",
                       (rv.subject or "math", title,
                        json.dumps({"source": "review", "student_name": rv.student_name,
                                    "subject": rv.subject or "math"}, ensure_ascii=False),
                        "auto"))
    paper_id = cur.lastrowid
    for i, q in enumerate(picked):
        conn.execute("INSERT INTO paper_questions (paper_id, question_id, position) VALUES (?,?,?)",
                     (paper_id, q["id"], i + 1))
    conn.commit()
    conn.close()
    return {"code": 200, "paper_id": paper_id, "title": title, "question_count": len(picked),
            "knowledge_points": [k for k, _ in kps]}


@router.get("/papers")
def list_papers(subject: str = "", source: str = ""):
    """试卷列表（教师端组卷管理/学生端指定卷用），含题数；source 可选过滤 teacher/auto"""
    conn = get_conn()
    sql = ("SELECT p.id, p.subject, p.title, p.config, p.create_time, p.source, "
           "COUNT(pq.question_id) q_count FROM papers p "
           "LEFT JOIN paper_questions pq ON pq.paper_id=p.id WHERE 1=1")
    params = []
    if subject:
        sql += " AND p.subject=?"
        params.append(subject)
    if source:
        sql += " AND p.source=?"
        params.append(source)
    rows = conn.execute(sql + " GROUP BY p.id ORDER BY p.create_time DESC, p.id DESC", params).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["config"] = json.loads(d.get("config") or "{}")
        except Exception:
            d["config"] = {}
        items.append(d)
    conn.close()
    return {"code": 200, "items": items}


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: int):
    """删除试卷（级联删题目关联）"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM papers WHERE id=?", (paper_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="试卷不存在")
    conn.execute("DELETE FROM paper_questions WHERE paper_id=?", (paper_id,))
    conn.execute("DELETE FROM papers WHERE id=?", (paper_id,))
    conn.commit()
    conn.close()
    return {"code": 200}


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int, with_answers: int = 0):
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
    # 学生作答时不下发答案；教师预览（with_answers=1）保留答案/解析
    if not with_answers:
        for q in questions:
            q["answer"] = ""
            q["analysis"] = ""
    conn.close()
    return {"code": 200, "paper": p, "questions": questions}


def _pick_by_difficulty(n, difficulties, by_diff, pool):
    """按难度配比抽题：先按比例取整，再轮转补齐余数；某难度不足则缺额均摊给有题的难度。

    返回抽取到的题目列表（顺序已 shuffle）。
    """
    if n <= 0:
        return []
    diffs = ["easy", "medium", "hard"]
    ratios = {d: difficulties.get(d, 0) or 0 for d in diffs}
    total_r = sum(ratios.values()) or 100
    # 先按比例取整
    quota = {d: int(n * ratios[d] / total_r) for d in diffs}
    # 轮转补齐余数（比例大的优先补）
    remain = n - sum(quota.values())
    order = sorted(diffs, key=lambda d: -ratios[d])
    for i in range(remain):
        quota[order[i % len(diffs)]] += 1
    # 每难度从池子取 quota[d] 道；不足则该难度少取
    chosen = []
    for d in diffs:
        avail = by_diff.get(d, [])
        take = min(quota[d], len(avail))
        chosen.extend(avail[:take])
    # 若因某难度池不足有缺额，从剩余池子（已 shuffle）补齐
    if len(chosen) < n:
        used = {q["id"] for q in chosen}
        extra = [q for q in pool if q["id"] not in used]
        random.shuffle(extra)
        for q in extra:
            if len(chosen) >= n:
                break
            chosen.append(q)
    return chosen


def judge_question(q, student_answer, short_score=None, short_needs_review=False):
    """判单题，返回 (得分0/1, 是否正确, 标准答案)

    short_score: 简答题 AI 批量判分结果（0~1）；None 表示未评分（判 0 分 + needs_review 标记）
    """
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
    # short 简答题 → AI 批量判分（score 已算好传入）；未作答/未评分判 0 分
    if qtype == "short":
        if not stu:
            return (0.0, False, ans)
        score = short_score if short_score is not None else 0.0
        return (score, score >= 0.6, ans)
    return (0.0, False, ans)


def ai_grade_short_batch(pairs):
    """一次 DeepSeek 调用给多道简答题评分。

    pairs: [(qid, stem, answer, student_answer), ...]  qid 为 str
    返回 {qid: 0~1 得分率}；解析失败/网络异常返回 {}（调用方逐题兜底 0 分 + needs_review）
    """
    if not pairs:
        return {}
    lines = []
    for qid, stem, answer, stu in pairs:
        lines.append(f"{qid}. 题目：{stem}\n   参考答案要点：{answer}\n   学生答案：{stu}")
    prompt = (
        "你是阅卷老师，请给以下每道简答题的作答评分（得分率 0~1）。\n\n"
        + "\n\n".join(lines) + "\n\n"
        "只输出一个 JSON 对象，键为题号（如 " + str(pairs[0][0]) + "），值为 0 到 1 之间的得分率（保留两位小数），"
        "不要输出其他任何内容。例如：{\"" + str(pairs[0][0]) + "\": 0.85}"
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 512,
    }
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        txt = data["choices"][0]["message"]["content"].strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            txt = txt[start:end + 1]
        obj = json.loads(txt)
        result = {}
        for k, v in obj.items():
            key = str(k).strip()
            try:
                result[key] = max(0.0, min(1.0, float(v)))
            except Exception:
                continue
        return result
    except Exception:
        return {}


@router.post("/papers/{paper_id}/submit")
def submit_paper(paper_id: int, sub: SubmitIn):
    conn = get_conn()
    paper = conn.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
    if not paper:
        conn.close()
        raise HTTPException(status_code=404, detail="试卷不存在")
    try:
        pconfig = json.loads(paper["config"] or "{}")
    except Exception:
        pconfig = {}
    qrows = conn.execute(
        "SELECT q.* FROM questions q JOIN paper_questions pq ON q.id=pq.question_id "
        "WHERE pq.paper_id=? ORDER BY pq.position", (paper_id,)
    ).fetchall()
    questions = [row_to_dict(r) for r in qrows]

    # 简答题批量 AI 判分（一次 DeepSeek 调用），失败逐题兜底
    short_pairs = [
        (str(q["id"]), q["stem"], q.get("answer") or "", sub.answers.get(str(q["id"]), ""))
        for q in questions if q["qtype"] == "short" and (sub.answers.get(str(q["id"]), "") or "").strip()
    ]
    short_scores = ai_grade_short_batch(short_pairs) if short_pairs else {}

    total = 0.0
    score = 0.0
    results = {}
    for q in questions:
        qid = str(q["id"])
        stu_ans = sub.answers.get(qid, "")
        if q["qtype"] == "short" and stu_ans.strip():
            s = short_scores.get(qid)
            needs_review = s is None
            pts, correct, std_ans = judge_question(q, stu_ans, short_score=s if s is not None else 0.0)
        else:
            needs_review = False
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
        if needs_review:
            results[qid]["needs_review"] = True
        # 错题归集
        if not correct:
            conn.execute(
                "INSERT OR IGNORE INTO wrong_book (student_name, subject, question_id, attempt_id) VALUES (?,?,?,?)",
                (sub.student_name, paper["subject"], q["id"], 0),
            )

    # 错题重练卷：做对 → mastered=1，做错 → redo_count+1（形成巩固闭环）
    if pconfig.get("source") == "review":
        for qid, r in results.items():
            try:
                qid_int = int(qid)
            except Exception:
                continue
            if r["correct"]:
                conn.execute(
                    "UPDATE wrong_book SET mastered=1, redo_count=redo_count+1 WHERE student_name=? AND question_id=?",
                    (sub.student_name, qid_int))
            else:
                conn.execute(
                    "UPDATE wrong_book SET redo_count=redo_count+1 WHERE student_name=? AND question_id=?",
                    (sub.student_name, qid_int))

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
