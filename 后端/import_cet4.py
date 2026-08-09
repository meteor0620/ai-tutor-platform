# -*- coding: utf-8 -*-
"""
把 cet4_bank_final.json 导入 aiplatform.db 题库(2026-08-09)

- 阅读单选(source=real, qtype=single, knowledge_point=阅读, 带 passage/passage_key)
- 翻译简答(source=real, qtype=short, knowledge_point=翻译, AI判分)
幂等: 先删除 source='real' 的旧题再插入。
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "aiplatform.db")


def ensure_columns(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    for c, ddl in (("passage", "TEXT DEFAULT ''"), ("passage_key", "TEXT DEFAULT ''")):
        if c not in cols:
            conn.execute(f"ALTER TABLE questions ADD COLUMN {c} {ddl}")
            print(f"新增列: {c}")


def main():
    bank = json.load(open(os.path.join(BASE, "cet4_bank_final.json"), encoding="utf-8"))
    conn = sqlite3.connect(DB)
    ensure_columns(conn)
    n_del = conn.execute("DELETE FROM questions WHERE subject='english' AND source='real'").rowcount
    conn.commit()
    print(f"清除旧 real 题: {n_del}")

    # 阅读单选
    n_read = 0
    for p in bank["papers"]:
        passage = p["passage"]
        key = p["passage_key"]
        for q in p["questions"]:
            opts = json.dumps(q["options"], ensure_ascii=False)
            conn.execute(
                "INSERT INTO questions (subject,knowledge_point,qtype,difficulty,stem,options,answer,analysis,source,passage,passage_key) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("english", "阅读", "single", "medium", q["stem"], opts, q["answer"], q["analysis"],
                 "real", passage, key))
            n_read += 1

    # 翻译简答
    n_trans = 0
    for t in bank["translations"]:
        stem = "【四级翻译真题】请将下面的段落翻译成英文，尽量忠实、通顺、完整：\n\n" + t["stem"]
        analysis = "参考译文已给出。注意：翻译时先理解中文大意，再组织英文结构；动笔前确定时态与主谓一致，专有名词可保留拼音/意译。"
        conn.execute(
            "INSERT INTO questions (subject,knowledge_point,qtype,difficulty,stem,options,answer,analysis,source,passage,passage_key) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("english", "翻译", "short", "medium", stem, "[]", t["answer"], analysis, "real", "", ""))
        n_trans += 1

    conn.commit()
    conn.close()
    print(f"导入完成: 阅读单选 {n_read} 题, 翻译简答 {n_trans} 题")


if __name__ == "__main__":
    main()
