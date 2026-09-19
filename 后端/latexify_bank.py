# -*- coding: utf-8 -*-
r"""
数学题库 LaTeX 化：把 questions 表 math 科目的 stem/options/analysis 里的
伪数学记号（lim(x→0)、e^x、x²、(−∞,0) 等）改写成标准 LaTeX（$...$ / $$...$$）。
- DeepSeek 逐题改写（4 并发），answer 字段绝不改（判分依赖）
- 改写前整表备份到 bank_backup_math_<date>.json
- 严格校验：选项字母前缀不变、题干非空、JSON 可解析，失败则保留原文
- 仅动 math 科目；english 不碰
运行：PYTHONIOENCODING=utf-8 python latexify_bank.py
"""
import concurrent.futures as cf
import io
import json
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from database import DB_PATH
from config import get

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
KEY = get("DEEPSEEK_KEY", "")

PROMPT = r"""你是数学教材编辑。把下面数学题里的数学记号改写成标准 LaTeX（行内公式用 $...$ 包裹，独立公式用 $$...$$）。
要求：
1. 只改数学记号的写法；中文文字、标点、题意、数字、选项字母前缀（如 "A. "）完全不变
2. 典型转换：lim(x→0) → $\lim\limits_{x \to 0}$；x² → $x^2$；e^x → $e^x$；
   a/b 分式 → $\frac{a}{b}$；区间 (−∞,0) → $(-\infty, 0)$；f'(x) → $f'(x)$；dy/dx → $\frac{dy}{dx}$
3. 填空占位 ____ 原样保留；没有数学内容的字段原样返回
4. options 数组每项必须保持 "字母. 内容" 的前缀格式，字母不得改动
5. 输出严格 JSON：{"stem": "...", "options": ["A. ...", ...], "analysis": "..."}
   （options/analysis 原文为空则返回空数组/空字符串；analysis 里没有数学就原样返回）"""

MATH_MARKER = re.compile(r"[0-9^_√∫∑∏∞→←↑↓≠≈≥≤±×÷∂πΔ∇\-/]|sin|cos|tan|lim|log|ln|sup|inf")


def call_llm(q):
    body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps({
                "stem": q["stem"],
                "options": json.loads(q["options"] or "[]"),
                "analysis": q["analysis"] or "",
            }, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 4096,
    }
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(body).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # strict=False：容忍模型在 JSON 字符串里输出裸换行/控制符
    out = json.loads(data["choices"][0]["message"]["content"], strict=False)
    stem = (out.get("stem") or "").strip()
    opts = out.get("options")
    opts = [str(o) for o in opts] if isinstance(opts, list) else []
    analysis = (out.get("analysis") or "").strip()
    # ---- 校验：不过关返回 None（保留原文） ----
    if not stem:
        return None
    orig_opts = json.loads(q["options"] or "[]")
    if orig_opts:
        if len(opts) != len(orig_opts):
            return None
        for a, b in zip(orig_opts, opts):
            if not b.startswith(a[0] + "."):
                return None
    if MATH_MARKER.search(q["stem"] or "") and stem == q["stem"]:
        pass  # 没改也算过（可能本来就没数学）
    return {"stem": stem, "options": json.dumps(opts, ensure_ascii=False) if orig_opts else q["options"],
            "analysis": analysis if q["analysis"] else q["analysis"]}


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM questions WHERE subject='math' ORDER BY id").fetchall()]
    print(f"数学题共 {len(rows)} 题")

    # 备份
    backup = f"bank_backup_math_{time.strftime('%Y%m%d_%H%M%S')}.json"
    json.dump(rows, open(backup, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已备份 -> {backup}")

    todo = [r for r in rows if MATH_MARKER.search(r["stem"] or "")]
    print(f"含数学记号待处理: {len(todo)} 题")
    done, fail = 0, 0

    def work(q):
        for _ in range(3):  # 重试 3 次
            try:
                return q["id"], call_llm(q)
            except Exception as e:
                err = str(e)[:120]
                time.sleep(1.5)
        return q["id"], None, err

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(work, todo):
            if len(res) == 3:
                print(f"  #{res[0]} 失败: {res[2]}")
                fail += 1
                continue
            qid, out = res
            if out is None:
                print(f"  #{qid} 校验不过，保留原文")
                fail += 1
                continue
            conn.execute("UPDATE questions SET stem=?, options=?, analysis=? WHERE id=?",
                         (out["stem"], out["options"], out["analysis"], qid))
            conn.commit()
            done += 1
            if done % 20 == 0:
                print(f"  进度 {done}/{len(todo)}", flush=True)
    conn.close()
    print(f"完成：改写 {done} 题，失败/跳过 {fail} 题")


if __name__ == "__main__":
    main()
