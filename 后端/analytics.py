"""学情分析 API：聚合测试/错题数据，输出看板所需统计 + 学生明细 + AI 诊断报告"""
import json
import urllib.request
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn, row_to_dict
from config import get

router = APIRouter(prefix="/api/analytics", tags=["学情分析"])

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY = get("DEEPSEEK_KEY", "")  # 从 .env 读取, 勿硬编码

SUBJECT_NAMES = {"math": "高等数学", "english": "大学英语"}


class ReportIn(BaseModel):
    subject: str
    student_name: str = ""  # 空 = 班级报告
    refresh: bool = False   # True 强制重新生成


def call_deepseek(prompt: str, temperature: float = 0.5) -> str:
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _all_attempts(subject: str = "", student_name: str = ""):
    """读取 attempts，可过滤科目/学生，返回列表（results 已解析为 dict）"""
    conn = get_conn()
    sql = "SELECT * FROM attempts WHERE 1=1"
    params = []
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if student_name:
        sql += " AND student_name=?"
        params.append(student_name)
    rows = conn.execute(sql + " ORDER BY create_time, id", params).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["results"] = json.loads(d.get("results") or "{}")
        except Exception:
            d["results"] = {}
        items.append(d)
    return items


@router.get("/overview")
def overview(subject: str = ""):
    """班级总览：测试次数、学生数、平均分、最高/最低、及格率、总正确率、错题总数"""
    attempts = _all_attempts(subject)
    conn = get_conn()
    students = set()
    total_score, correct_cnt, all_cnt = 0.0, 0, 0
    scores = []
    for a in attempts:
        students.add(a["student_name"])
        total_score += a["score"]
        scores.append(a["score"])
        for qid, r in a["results"].items():
            all_cnt += 1
            if r.get("correct"):
                correct_cnt += 1
    # 错题总数（去重：同一学生同一题算一次）
    wsql = "SELECT count(*) c FROM wrong_book WHERE 1=1"
    wparams = []
    if subject:
        wsql += " AND subject=?"
        wparams.append(subject)
    wrong_cnt = conn.execute(wsql, wparams).fetchone()["c"]
    conn.close()

    n = len(attempts)
    pass_cnt = len([s for s in scores if s >= 60])
    return {
        "code": 200,
        "tests": n,
        "students": len(students),
        "avg": round(total_score / n, 1) if n else 0,
        "max": max(scores) if scores else 0,
        "min": min(scores) if scores else 0,
        "pass_rate": round(pass_cnt / n * 100, 1) if n else 0,
        "accuracy": round(correct_cnt / all_cnt * 100, 1) if all_cnt else 0,
        "wrong_count": wrong_cnt,
    }


@router.get("/knowledge")
def knowledge(subject: str = ""):
    """按知识点聚合掌握度（来自逐题判卷结果）"""
    attempts = _all_attempts(subject)
    agg = defaultdict(lambda: {"total": 0, "correct": 0})
    for a in attempts:
        for qid, r in a["results"].items():
            kp = (r.get("knowledge_point") or "未分类").strip() or "未分类"
            agg[kp]["total"] += 1
            if r.get("correct"):
                agg[kp]["correct"] += 1
    items = [
        {
            "knowledge_point": kp,
            "total": v["total"],
            "correct": v["correct"],
            "accuracy": round(v["correct"] / v["total"] * 100, 1) if v["total"] else 0,
        }
        for kp, v in sorted(agg.items(), key=lambda x: -x[1]["total"])
    ]
    return {"code": 200, "items": items}


@router.get("/trends")
def trends(subject: str = "", student_name: str = ""):
    """分数趋势：按测试时间线聚合平均分"""
    attempts = _all_attempts(subject, student_name)
    by_time = defaultdict(lambda: {"sum": 0, "count": 0})
    for a in attempts:
        t = (a["create_time"] or "")[:10]  # 取日期 YYYY-MM-DD
        by_time[t]["sum"] += a["score"]
        by_time[t]["count"] += 1
    items = [
        {
            "date": t,
            "avg_score": round(v["sum"] / v["count"], 1),
            "count": v["count"],
        }
        for t, v in sorted(by_time.items())
    ]
    return {"code": 200, "items": items}


@router.get("/wrong")
def wrong(subject: str = ""):
    """错题分布：按知识点统计错题数（含题型细分）"""
    conn = get_conn()
    sql = ("SELECT q.knowledge_point, q.qtype, count(*) c "
           "FROM wrong_book wb JOIN questions q ON wb.question_id=q.id "
           "WHERE wb.mastered=0")
    params = []
    if subject:
        sql += " AND q.subject=?"
        params.append(subject)
    rows = conn.execute(sql + " GROUP BY q.knowledge_point, q.qtype", params).fetchall()
    conn.close()
    kp_agg = defaultdict(lambda: {"count": 0, "qtypes": defaultdict(int)})
    for r in rows:
        kp = (r["knowledge_point"] or "未分类").strip() or "未分类"
        kp_agg[kp]["count"] += r["c"]
        kp_agg[kp]["qtypes"][r["qtype"]] += r["c"]
    items = [
        {
            "knowledge_point": kp,
            "count": v["count"],
            "qtypes": dict(v["qtypes"]),
        }
        for kp, v in sorted(kp_agg.items(), key=lambda x: -x[1]["count"])
    ]
    return {"code": 200, "items": items}


@router.get("/students")
def students(subject: str = ""):
    """学生列表：测试次数、平均分、最近分数、错题数（按最近活跃排序）"""
    attempts = _all_attempts(subject)
    agg = defaultdict(lambda: {"count": 0, "sum": 0.0, "latest": ("", 0)})
    for a in attempts:
        s = agg[a["student_name"]]
        s["count"] += 1
        s["sum"] += a["score"]
        if (a["create_time"] or "") > s["latest"][0]:
            s["latest"] = (a["create_time"] or "", a["score"])
    conn = get_conn()
    wsql = "SELECT student_name, count(*) c FROM wrong_book WHERE mastered=0"
    wparams = []
    if subject:
        wsql += " AND subject=?"
        wparams.append(subject)
    wrong_cnt = {r["student_name"]: r["c"] for r in conn.execute(wsql + " GROUP BY student_name", wparams).fetchall()}
    conn.close()

    items = []
    for name, s in agg.items():
        items.append({
            "student_name": name,
            "tests": s["count"],
            "avg": round(s["sum"] / s["count"], 1) if s["count"] else 0,
            "latest_score": s["latest"][1],
            "latest_time": s["latest"][0],
            "wrong_count": wrong_cnt.get(name, 0),
        })
    items.sort(key=lambda x: x["latest_time"], reverse=True)
    return {"code": 200, "items": items}


@router.get("/students/{name}/detail")
def student_detail(name: str, subject: str = ""):
    """单个学生详情：历次成绩 + 知识点掌握度 + 错题清单"""
    attempts = _all_attempts(subject, name)
    attempts_out = []
    for a in attempts:
        n = len(a["results"])
        correct = sum(1 for r in a["results"].values() if r.get("correct"))
        attempts_out.append({
            "attempt_id": a["id"], "paper_id": a["paper_id"],
            "score": a["score"], "total": a["total"],
            "create_time": a["create_time"], "correct": correct, "total_q": n,
        })
    agg = defaultdict(lambda: {"total": 0, "correct": 0})
    for a in attempts:
        for r in a["results"].values():
            kp = (r.get("knowledge_point") or "未分类").strip() or "未分类"
            agg[kp]["total"] += 1
            if r.get("correct"):
                agg[kp]["correct"] += 1
    knowledge = [
        {"knowledge_point": kp, "total": v["total"], "correct": v["correct"],
         "accuracy": round(v["correct"] / v["total"] * 100, 1) if v["total"] else 0}
        for kp, v in sorted(agg.items(), key=lambda x: -x[1]["total"])
    ]
    conn = get_conn()
    wsql = ("SELECT wb.*, q.subject, q.knowledge_point, q.qtype, q.stem, q.options, q.answer, q.analysis "
            "FROM wrong_book wb JOIN questions q ON wb.question_id=q.id WHERE wb.student_name=?")
    wparams = [name]
    if subject:
        wsql += " AND q.subject=?"
        wparams.append(subject)
    wrong = [row_to_dict(r) for r in conn.execute(wsql + " ORDER BY wb.wrong_time DESC", wparams).fetchall()]
    conn.close()
    return {"code": 200, "student_name": name, "attempts": attempts_out,
            "knowledge": knowledge, "wrong": wrong}


def _build_individual_report_text(name: str, subject: str) -> str:
    """单个学生诊断报告 prompt 数据"""
    detail = student_detail(name, subject)
    lines = []
    lines.append(f"学生：{name}；科目：{SUBJECT_NAMES.get(subject, subject)}")
    if detail["attempts"]:
        lines.append("历次自测成绩（时间 分数/满分）：")
        for a in detail["attempts"]:
            lines.append(f"- {a['create_time']}  {a['score']}/{a['total']}  （对{a['correct']}/{a['total_q']}题）")
    else:
        lines.append("该生暂无自测记录。")
    if detail["knowledge"]:
        lines.append("知识点掌握度（知识点 正确/总 正确率）：")
        for k in detail["knowledge"]:
            lines.append(f"- {k['knowledge_point']}  {k['correct']}/{k['total']}  {k['accuracy']}%")
    if detail["wrong"]:
        lines.append("该生错题（最多列 12 条，按时间倒序）：")
        for w in detail["wrong"][:12]:
            lines.append(f"- [{w['knowledge_point']}] {w['stem'][:80]}")
    return "\n".join(lines)


def _build_class_report_text(subject: str) -> str:
    """班级学情报告 prompt 数据"""
    ov = overview(subject)
    kn = knowledge(subject)["items"]
    wr = wrong(subject)["items"]
    tr = trends(subject)["items"]
    lines = []
    lines.append(f"科目：{SUBJECT_NAMES.get(subject, subject)}")
    lines.append(
        f"班级总览：测试 {ov['tests']} 次、学生 {ov['students']} 人、平均分 {ov['avg']}、"
        f"最高 {ov['max']}、最低 {ov['min']}、及格率 {ov['pass_rate']}%、总正确率 {ov['accuracy']}%、错题 {ov['wrong_count']} 题")
    if tr:
        lines.append("平均分趋势（日期 平均分）：")
        for t in tr[-10:]:
            lines.append(f"- {t['date']}  {t['avg_score']}  （{t['count']}次）")
    if kn:
        lines.append("知识点掌握度：")
        for k in kn:
            lines.append(f"- {k['knowledge_point']}  {k['accuracy']}%  （{k['total']}题）")
    if wr:
        lines.append("错题分布（知识点 错题数 题型分布）：")
        for w in wr[:10]:
            qts = "、".join(f"{qt}×{c}" for qt, c in w["qtypes"].items())
            lines.append(f"- {w['knowledge_point']}  {w['count']}  （{qts}）")
    return "\n".join(lines)


def _report_prompt(subject: str, data_text: str, individual: bool) -> str:
    subj = SUBJECT_NAMES.get(subject, subject)
    role = (f"正在为一名学生撰写『{subj}·AI 个性化学习诊断报告』"
            if individual else f"正在为整个班级撰写『{subj}·AI 班级学情分析报告』")
    extra = "\n## 教学建议\n给出 2-4 条面向教师的可操作教学改进建议。" if not individual else ""
    return (
        f"你是一位经验丰富的{subj}教师，{role}。\n"
        f"基于以下真实数据撰写报告（不得编造数据）：\n\n{data_text}\n\n"
        f"请用 markdown 输出，结构固定为：\n"
        f"## 总体评价\n## 分数趋势分析\n## 知识点掌握分析\n## 错题归因\n## 针对性学习建议"
        f"{extra}\n"
        f"每节 2-5 行，语言专业、积极、具体可操作。只输出报告正文。"
    )


@router.post("/report")
def report(r: ReportIn):
    """AI 学情诊断报告：个人（student_name 非空）或班级（空）。结果缓存到 reports 表"""
    conn = get_conn()
    key = (r.student_name or "", r.subject)
    if not r.refresh:
        row = conn.execute(
            "SELECT content, create_time FROM reports WHERE student_name=? AND subject=?",
            key).fetchone()
        if row and row["content"]:
            conn.close()
            return {"code": 200, "cached": True, "content": row["content"], "create_time": row["create_time"]}
    conn.close()

    if r.student_name:
        data_text = _build_individual_report_text(r.student_name, r.subject)
        prompt = _report_prompt(r.subject, data_text, individual=True)
    else:
        data_text = _build_class_report_text(r.subject)
        prompt = _report_prompt(r.subject, data_text, individual=False)

    try:
        content = call_deepseek(prompt).strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"诊断报告生成失败: {str(e)[:200]}")

    conn = get_conn()
    conn.execute(
        "INSERT INTO reports (student_name, subject, content) VALUES (?,?,?) "
        "ON CONFLICT(student_name, subject) DO UPDATE SET content=excluded.content, "
        "create_time=datetime('now','localtime')",
        (r.student_name or "", r.subject, content))
    conn.commit()
    conn.close()
    return {"code": 200, "cached": False, "content": content}
