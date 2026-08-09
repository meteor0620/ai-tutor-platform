"""学情演示数据生成脚本
用法: python seed_demo.py
说明: 清空题库/试卷/作答/错题表, 生成 30 道高数题、3 张试卷、10 名学生作答记录与错题本,
      供学情分析看板演示。真实使用前可重新跑本脚本重置为演示数据。
"""
import json
import random
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aiplatform.db")

# 确保表结构存在(后端首次启动会自动建表;此处显式建表以便独立运行 seed)
from database import init_db
init_db()

# (知识点, 题干, 题型, 难度, 选项, 答案, 解析)
QUESTIONS = [
    # ---- 极限 ----
    ("极限", "lim(x→0) sin x / x 的值为?", "single", "easy", '["A. 0","B. 1","C. ∞","D. 不存在"]', "B", "重要极限：lim(x→0) sin x / x = 1"),
    ("极限", "lim(x→∞) (1 + 1/x)^x = ?", "single", "easy", '["A. 1","B. e","C. e^2","D. ∞"]', "B", "第二个重要极限，等于自然常数 e"),
    ("极限", "无穷小量与无穷大量之和为无穷小量。", "judge", "medium", None, "错", "无穷小加无穷大仍为无穷大"),
    ("极限", "数列 {1/n} 当 n→∞ 时收敛到 0。", "judge", "easy", None, "对", "1/n → 0"),
    ("极限", "lim(x→0) (e^x − 1)/x = ____", "blank", "medium", None, "1", "等价无穷小：e^x − 1 ~ x"),
    # ---- 导数 ----
    ("导数", "f(x)=x² 在 x=1 处的导数为?", "single", "easy", '["A. 1","B. 2","C. 0","D. 3"]', "B", "f'(x)=2x, f'(1)=2"),
    ("导数", "导数的几何意义是曲线在某点的____斜率。", "blank", "easy", None, "切线", "导数几何意义为切线斜率"),
    ("导数", "若 f(x) 在 x₀ 处可导，则 f(x) 在 x₀ 处一定连续。", "judge", "easy", None, "对", "可导必连续"),
    ("导数", "设 y = sin(2x)，则 dy/dx = ?", "single", "medium", '["A. cos2x","B. 2cos2x","C. −cos2x","D. sin2x"]', "B", "链式法则：dy/dx = 2cos2x"),
    ("导数", "函数 y = x³ 的单调递增区间是？", "single", "medium", '["A. (−∞,0)","B. (0,+∞)","C. (−∞,+∞)","D. (−1,1)"]', "C", "y'=3x²≥0 恒成立，全区间单调递增"),
    ("导数", "求 y = ln x 的导数：____", "blank", "easy", None, "1/x", "(ln x)' = 1/x"),
    # ---- 积分 ----
    ("积分", "∫ x² dx = ?", "single", "easy", '["A. x³/3 + C","B. 2x + C","C. x³ + C","D. x²/3 + C"]', "A", "幂函数积分公式"),
    ("积分", "∫₀¹ 1 dx = ?", "single", "easy", '["A. 0","B. 1","C. 2","D. 1/2"]', "B", "定积分几何意义为矩形面积"),
    ("积分", "不定积分是求导的逆运算。", "judge", "easy", None, "对", "不定积分即原函数族"),
    ("积分", "∫ e^x dx = ____", "blank", "easy", None, "e^x+C", "指数函数积分"),
    ("积分", "用分部积分求 ∫ x·e^x dx 的结果是？", "single", "hard", '["A. (x−1)e^x+C","B. xe^x+C","C. (x+1)e^x+C","D. e^x+C"]', "A", "分部积分：∫x e^x dx = (x−1)e^x+C"),
    ("积分", "定积分 ∫₀^π sin x dx = ?", "blank", "medium", None, "2", "∫₀^π sin x dx = [−cos x]₀^π = 2"),
    # ---- 多元函数 ----
    ("多元函数", "z = x² + y² 在 (0,0) 处是否有极小值？", "judge", "medium", None, "对", "开口向上的抛物面，原点为极小值"),
    ("多元函数", "函数 z = x² + y² 的偏导数 ∂z/∂x = ?", "single", "easy", '["A. 2y","B. 2x","C. x+y","D. 0"]', "B", "对 x 求偏导，y 视为常数"),
    ("多元函数", "求 ∂z/∂y：z = x·y²，在点 (1,2) 处 ∂z/∂y = ?", "blank", "medium", None, "4", "∂z/∂y = 2xy，代入得 4"),
    ("多元函数", "多元函数在某点偏导数存在是该点连续的充分条件。", "judge", "medium", None, "错", "偏导数存在不一定连续"),
    ("多元函数", "z = sin(xy) 的混合偏导 ∂²z/∂x∂y = ?", "single", "hard", '["A. cos(xy)","B. −sin(xy)","C. xy·cos(xy)","D. sin(xy) − xy·cos(xy)"]', "C", "∂z/∂x = y·cos(xy)，再对 y 求导得 cos(xy) − xy·sin(xy)，验证为 C"),
    # ---- 微分方程 ----
    ("微分方程", "微分方程 y' = y 的通解是？", "single", "medium", '["A. y = Ce^x","B. y = Ce^−x","C. y = Cx","D. y = C"]', "A", "分离变量：dy/y = dx，ln y = x + C"),
    ("微分方程", "y'' = 0 的通解为 y = C₁x + C₂。", "judge", "easy", None, "对", "二阶积分两次"),
    ("微分方程", "方程 y' + y = 0 的通解为 y = Ce^(−x)。", "judge", "easy", None, "对", "特征根 r = −1"),
    ("微分方程", "解方程 dy/dx = 2x 的通解：____", "blank", "easy", None, "x^2+C", "直接积分"),
    ("微分方程", "微分方程 y' = 2xy 的通解为？", "single", "hard", '["A. y = Ce^(x²)","B. y = Ce^(−x²)","C. y = C/x","D. y = Ce^x"]', "A", "分离变量积分得 ln y = x² + C"),
    # ---- 级数 ----
    ("级数", "等比级数 Σ 1/2^n 是否收敛？", "judge", "easy", None, "对", "公比 1/2 < 1，收敛到 1"),
    ("级数", "级数 Σ 1/n 收敛。", "judge", "easy", None, "错", "调和级数发散"),
    ("级数", "幂级数 Σ x^n/n! 的和函数为？", "single", "hard", '["A. e^x","B. e^−x","C. 1/(1−x)","D. sin x"]', "A", "e^x 的泰勒展开"),
]

# (知识点, 题干, 题型, 难度, 选项, 答案, 解析) —— 英语
QUESTIONS_EN = [
    ("词汇", "单词 'abandon' 的意思是？", "single", "easy", '["A. 放弃","B. 增加","C. 忍受","D. 接受"]', "A", "abandon = 放弃"),
    ("词汇", "'significant' 的同义词是？", "single", "medium", '["A. important","B. small","C. sudden","D. brief"]', "A", "significant ≈ important"),
    ("词汇", "动词 'conduct' 的名词形式是 ____", "blank", "medium", None, "conduct(ion)", "conduct → conduction / conduct"),
    ("词汇", "'benefit' 意为'利益、好处'。", "judge", "easy", None, "对", "benefit = 利益/好处"),
    ("词汇", "'purchase' 意为'购买'。", "judge", "easy", None, "对", "purchase = 购买"),
    ("语法", "She ___ to school every day. (go)", "blank", "easy", None, "goes", "第三人称单数加 es"),
    ("语法", "I have ___ finished my homework. (already/yet)", "blank", "medium", None, "already", "肯定句用 already"),
    ("语法", "'If it rains tomorrow, we ___ stay at home.' 应填 will。", "judge", "medium", None, "对", "主将从现"),
    ("语法", "定语从句中 which 指代____。", "blank", "medium", None, "物", "which 指物"),
    ("语法", "'Not only he but also I ___ a student.' 应填 am。", "judge", "hard", None, "错", "就近原则, I 为主语用 am, 句子本身是对的"),
    ("阅读", "阅读理解主要考查学生对文章____的把握。", "blank", "easy", None, "主旨", "考查主旨大意"),
    ("阅读", "细节题应在原文中找到____。", "blank", "medium", None, "依据", "细节题需定位原文"),
    ("阅读", "推断题的答案通常____在文中直接出现。", "judge", "medium", None, "错", "推断题需推理, 不直接出现"),
    ("写作", "写英语作文时建议使用____句以提升档次。", "blank", "medium", None, "复合句", "复合句提升文章档次"),
    ("写作", "作文结尾通常需要总结____。", "blank", "easy", None, "观点", "结尾总结观点"),
    ("写作", "一篇优秀作文必须有标题和分段。", "judge", "easy", None, "对", "结构完整是得分要点"),
    ("听力", "听力题通常要求捕捉____信息。", "blank", "easy", None, "关键", "捕捉关键信息"),
    ("翻译", "中译英时应注意时态和____一致。", "blank", "hard", None, "主谓", "主谓一致"),
]

# 英语学生(姓名, 词汇/语法/阅读/写作/听力/翻译 掌握度)
STUDENTS_EN = [
    ("张伟", 0.78, 0.72, 0.80, 0.70, 0.75, 0.68),
    ("李娜", 0.85, 0.88, 0.90, 0.82, 0.86, 0.80),
    ("王强", 0.60, 0.55, 0.62, 0.58, 0.60, 0.52),
    ("刘洋", 0.74, 0.70, 0.76, 0.72, 0.73, 0.70),
    ("陈静", 0.92, 0.90, 0.88, 0.94, 0.90, 0.88),
    ("杨帆", 0.55, 0.60, 0.52, 0.48, 0.58, 0.54),
    ("赵敏", 0.80, 0.76, 0.82, 0.78, 0.79, 0.75),
    ("孙浩", 0.65, 0.58, 0.60, 0.55, 0.62, 0.60),
    ("周婷", 0.86, 0.84, 0.88, 0.85, 0.87, 0.83),
    ("吴磊", 0.50, 0.52, 0.48, 0.45, 0.50, 0.46),
]

KP_ORDER_EN = ["词汇", "语法", "阅读", "写作", "听力", "翻译"]

KP_ORDER = ["极限", "导数", "积分", "多元函数", "微分方程", "级数"]

# 数学学生(姓名, 极限/导数/积分/多元/微分方程/级数 掌握度)
STUDENTS = [
    ("张伟",  0.85, 0.90, 0.80, 0.75, 0.70, 0.88),
    ("李娜",  0.90, 0.85, 0.88, 0.80, 0.82, 0.90),
    ("王强",  0.60, 0.70, 0.55, 0.50, 0.60, 0.58),
    ("刘洋",  0.75, 0.80, 0.72, 0.65, 0.68, 0.78),
    ("陈静",  0.95, 0.92, 0.90, 0.85, 0.88, 0.93),
    ("杨帆",  0.55, 0.65, 0.60, 0.70, 0.50, 0.60),
    ("赵敏",  0.80, 0.75, 0.78, 0.72, 0.76, 0.80),
    ("孙浩",  0.70, 0.60, 0.65, 0.58, 0.55, 0.66),
    ("周婷",  0.88, 0.86, 0.84, 0.90, 0.80, 0.86),
    ("吴磊",  0.50, 0.55, 0.48, 0.45, 0.52, 0.50),
]


SUBJECTS_DEF = [
    {
        "id": "math",
        "questions": QUESTIONS,
        "students": STUDENTS,
        "kp_order": KP_ORDER,
        "paper_cfgs": [
            {"single": 4, "judge": 3, "blank": 2, "multiple": 0, "short": 1},
            {"single": 4, "judge": 3, "blank": 3, "multiple": 0, "short": 0},
            {"single": 3, "judge": 2, "blank": 2, "multiple": 0, "short": 0},
        ],
    },
    {
        "id": "english",
        "questions": QUESTIONS_EN,
        "students": STUDENTS_EN,
        "kp_order": KP_ORDER_EN,
        "paper_cfgs": [
            {"single": 4, "judge": 3, "blank": 3, "multiple": 0, "short": 0},
            {"single": 3, "judge": 3, "blank": 3, "multiple": 0, "short": 0},
            {"single": 3, "judge": 2, "blank": 2, "multiple": 0, "short": 0},
        ],
    },
]


def main():
    random.seed(20260806)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for t in ("questions", "papers", "paper_questions", "attempts", "wrong_book"):
        cur.execute("DELETE FROM " + t)
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('questions','papers','attempts','wrong_book')")

    total_q, total_p, total_stu = 0, 0, 0
    base = datetime.now()

    for subj in SUBJECTS_DEF:
        sid = subj["id"]
        # 1. 题目
        q_ids = {}
        for kp, stem, qtype, diff, options, ans, analysis in subj["questions"]:
            cur.execute(
                "INSERT INTO questions (subject,knowledge_point,qtype,difficulty,stem,options,answer,analysis,source) VALUES (?,?,?,?,?,?,?,?,?)",
                (sid, kp, qtype, diff, stem, options or "[]", ans, analysis, "demo"),
            )
            q_ids.setdefault(kp, []).append(cur.lastrowid)
        total_q += len(subj["questions"])

        # 2. 试卷
        paper_qids = []
        for cfg in subj["paper_cfgs"]:
            picked = []
            for qtype, cnt in cfg.items():
                pool = [qid for kp in q_ids for qid in q_ids[kp]
                        if conn.execute("SELECT qtype FROM questions WHERE id=?", (qid,)).fetchone()[0] == qtype]
                random.shuffle(pool)
                picked.extend(pool[:cnt])
            paper_qids.append(picked)
            cur.execute("INSERT INTO papers (subject,title,config) VALUES (?,?,?)",
                        (sid, "%s自测卷 %d" % (sid, len(paper_qids)),
                         json.dumps({"counts": cfg, "difficulties": {}}, ensure_ascii=False)))
            pid = cur.lastrowid
            for i, qid in enumerate(picked):
                cur.execute("INSERT INTO paper_questions (paper_id,question_id,position) VALUES (?,?,?)",
                            (pid, qid, i + 1))
        total_p += len(paper_qids)

        # 3. 作答 + 错题
        for si, (name, *skills) in enumerate(subj["students"]):
            for pi, qids in enumerate(paper_qids):
                day_offset = (si + 1) + pi * 4
                ts = (base - timedelta(days=13 - day_offset)).strftime("%Y-%m-%d %H:%M:%S")
                results, score_sum = {}, 0.0
                for qid in qids:
                    row = cur.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
                    kp = row[2]
                    skill = skills[subj["kp_order"].index(kp)] if kp in subj["kp_order"] else 0.7
                    prob = max(0.05, min(0.98, skill + random.uniform(-0.15, 0.15)))
                    correct = random.random() < prob
                    score_sum += 1.0 if correct else 0.0
                    results[str(qid)] = {
                        "correct": bool(correct), "score": 1.0 if correct else 0.0,
                        "student_answer": row[6] if correct else "（错误作答）",
                        "std_answer": row[6], "analysis": row[7],
                        "stem": row[4], "qtype": row[3], "knowledge_point": kp,
                    }
                    if not correct:
                        cur.execute(
                            "INSERT OR IGNORE INTO wrong_book (student_name,subject,question_id,attempt_id) VALUES (?,?,?,?)",
                            (name, sid, qid, 0),
                        )
                final = round(score_sum / len(qids) * 100, 1) if qids else 0
                cur.execute(
                    "INSERT INTO attempts (paper_id,subject,student_name,score,total,answers,results,create_time) VALUES (?,?,?,?,?,?,?,?)",
                    (pi + 1, sid, name, final, 100, "{}", json.dumps(results, ensure_ascii=False), ts),
                )
                aid = cur.lastrowid
                cur.execute("UPDATE wrong_book SET attempt_id=? WHERE student_name=? AND attempt_id=0", (aid, name))
        total_stu += len(subj["students"])

    conn.commit()
    conn.close()
    print("演示数据已生成: %d 题, %d 张卷, %d 名学生(双科目)" % (total_q, total_p, total_stu))


if __name__ == "__main__":
    main()
