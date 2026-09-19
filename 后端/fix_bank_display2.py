# -*- coding: utf-8 -*-
r"""修复二：假单选转填空 + 填空答案剥 $（判分精确匹配兼容，显示由前端兜底）"""
import io
import re
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
changes = 0

# 1. 选项为空的单选题 -> 填空题（题干本身就是"值为 ______"句式）
for r in conn.execute(
    "SELECT id, stem FROM questions WHERE subject='math' AND qtype='single' "
    "AND (options IS NULL OR options='[]' OR options='')").fetchall():
    conn.execute("UPDATE questions SET qtype='blank' WHERE id=?", (r["id"],))
    print(f"1 #{r['id']} [single->blank] {r['stem'][:60]}")
    changes += 1
conn.commit()

# 2. blank 答案剥掉外层 $（判分是精确匹配；前端 MarkdownRender 会兜底渲染裸 LaTeX）
for r in conn.execute("SELECT id, answer FROM questions WHERE subject='math' AND qtype='blank'").fetchall():
    a = (r["answer"] or "").strip()
    m = re.fullmatch(r"\$(.*)\$", a, flags=re.S)
    if m and "$" not in m.group(1):
        conn.execute("UPDATE questions SET answer=? WHERE id=?", (m.group(1).strip(), r["id"]))
        print(f"2 #{r['id']} [blank] {a[:50]!r} -> {m.group(1).strip()[:44]!r}")
        changes += 1
conn.commit()
conn.close()
print(f"完成：{changes} 处")
