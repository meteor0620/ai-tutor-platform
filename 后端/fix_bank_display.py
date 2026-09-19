# -*- coding: utf-8 -*-
r"""
题库显示类数据修复（三步，带备份，逐条打印变更）：
A. single/multiple 答案不是选项字母 → 按选项内容匹配回字母（判分依赖字母，#208 类 bug）
B. blank 答案存成整条方程（含 "____" / "= "）→ 截取最后一个等号后的值
C. stem/analysis 里 $ 分隔符损坏（$$...$ / $...$$ 不配对）→ 修复为 $...$
   注意：blank 的 answer 故意不包 $（papers.py 判分是精确字符串匹配，包了学生就没法答），
   其 LaTeX 显示由前端 MarkdownRender 兜底渲染。
运行：PYTHONIOENCODING=utf-8 python fix_bank_display.py
"""
import io
import json
import re
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("CREATE TABLE IF NOT EXISTS questions_backup_20260905 AS SELECT * FROM questions")
print("已备份 questions -> questions_backup_20260905")


def opt_letter(options, target):
    """在选项里找内容与 target 相同的字母；比较时去掉 $、空格、首字母前缀"""
    def norm(s):
        s = (s or "").strip()
        s = re.sub(r"^[A-D]\.\s*", "", s)
        return re.sub(r"[\s$\\]", "", s)
    t = norm(target)
    for o in options:
        if norm(o[3:]) == t or norm(o) == t:
            return o[0]
    return None


changes = 0

# ---- A. 客观题答案必须是字母 ----
for r in conn.execute("SELECT id, qtype, options, answer FROM questions WHERE subject='math' AND qtype IN ('single','multiple')").fetchall():
    ans = (r["answer"] or "").strip()
    opts = json.loads(r["options"] or "[]") if (r["options"] or "[]") != "[]" else []
    if re.fullmatch(r"[A-D]+(,[A-D]+)*", ans.upper().replace(" ", "")):
        continue
    letter = opt_letter(opts, ans)
    if letter:
        conn.execute("UPDATE questions SET answer=? WHERE id=?", (letter, r["id"]))
        print(f"A #{r['id']} [{r['qtype']}] answer {ans!r} -> {letter!r}")
        changes += 1
    else:
        print(f"A !! #{r['id']} [{r['qtype']}] 无法匹配选项: answer={ans!r} opts={opts}")
conn.commit()

# ---- B. blank 答案含 "____" / 整条方程 -> 取最后一个等号后的值 ----
for r in conn.execute("SELECT id, stem, answer FROM questions WHERE subject='math' AND qtype='blank'").fetchall():
    ans = (r["answer"] or "").strip()
    if "____" not in ans and "=" not in ans:
        continue
    if "____" in ans or re.search(r"\\(lim|frac|int|sum)\b", ans):
        # 取最后一个 = 右侧（排除 <= >= 等关系符），去掉首尾 $ 与占位符
        parts = re.split(r"(?<![<>!=])=(?!=)", ans)
        val = parts[-1].strip().strip("$").strip()
        if val and len(val) <= 40 and "____" not in val:
            conn.execute("UPDATE questions SET answer=? WHERE id=?", (val, r["id"]))
            print(f"B #{r['id']} [blank] answer {ans!r} -> {val!r}")
            changes += 1
        else:
            print(f"B !! #{r['id']} [blank] 无法自动截取: {ans!r}")
conn.commit()

# ---- C. $ 分隔符损坏修复（stem/analysis/analysis）----
def fix_dollars(s):
    if not s:
        return s
    orig = s
    # $$X$（无闭合 $$） -> $X$；$X$$（开头单 $ 结尾双 $） -> $X$
    s = re.sub(r"\$\$([^$\n]*?)\$(?!\$)", r"$\1$", s)
    s = re.sub(r"(?<!\$)\$([^$\n]*?)\$\$", r"$\1$", s)
    return s if s != orig else None

for r in conn.execute("SELECT id, qtype, stem, analysis FROM questions WHERE subject='math'").fetchall():
    for f in ("stem", "analysis"):
        fixed = fix_dollars(r[f])
        if fixed:
            conn.execute(f"UPDATE questions SET {f}=? WHERE id=?", (fixed, r["id"]))
            print(f"C #{r['id']} [{r['qtype']}] {f} 分隔符修复")
            changes += 1
conn.commit()
conn.close()
print(f"\n完成：共 {changes} 处修复")
