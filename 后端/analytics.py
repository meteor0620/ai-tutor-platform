"""学情分析 API：聚合测试/错题数据，输出看板所需统计"""
import json
from collections import defaultdict

from fastapi import APIRouter

from database import get_conn

router = APIRouter(prefix="/api/analytics", tags=["学情分析"])


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
