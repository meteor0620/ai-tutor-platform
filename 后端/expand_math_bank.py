# -*- coding: utf-8 -*-
r"""
数学题库扩充（第二轮）：按高数大纲细分知识点批量生成，补齐现有库缺口。
- 15 个知识点（中值定理/导数应用/不定积分/定积分应用/曲线面积分/幂级数/空间几何...）
- 题型含 **简答题(short)**：现有库为 0，补上后「AI 判分」数学也有简答演示
- 所有数学记号强制 LaTeX（$...$），免二次清洗
- 与库内既有题目按归一化题干去重；题型/难度/选项前缀严格校验
- source='ai'，answer 字段判分依据照旧
运行：PYTHONIOENCODING=utf-8 python expand_math_bank.py
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
from config import get
from database import DB_PATH

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
KEY = get("DEEPSEEK_KEY", "")

# 知识点 -> {题型: 数量}（题型: single/blank/judge/short）
PLAN = {
    "极限与连续":            {"single": 4, "blank": 3, "judge": 2},
    "洛必达法则":            {"single": 4, "blank": 3, "judge": 2, "short": 1},
    "导数与微分":            {"single": 4, "blank": 3, "judge": 2, "short": 1},
    "微分中值定理":          {"single": 3, "blank": 2, "judge": 2, "short": 1},
    "导数的应用":            {"single": 4, "blank": 2, "judge": 2, "short": 1},
    "不定积分":              {"single": 4, "blank": 3, "judge": 2, "short": 1},
    "定积分":                {"single": 4, "blank": 3, "judge": 2, "short": 1},
    "定积分的应用":          {"single": 3, "blank": 2, "judge": 2, "short": 1},
    "微分方程":              {"single": 3, "blank": 2, "judge": 2, "short": 1},
    "多元函数微分学":        {"single": 3, "blank": 2, "judge": 2, "short": 1},
    "二重积分":              {"single": 3, "blank": 2, "judge": 1, "short": 1},
    "三重积分与曲线曲面积分": {"single": 3, "blank": 1, "judge": 1},
    "常数项级数":            {"single": 3, "blank": 2, "judge": 2},
    "幂级数与函数展开":      {"single": 3, "blank": 1, "judge": 1},
    "空间解析几何与向量代数": {"single": 3, "blank": 1, "judge": 1},
}

QTYPE_LINE = {
    "single": "全部为单选题：4 个选项，格式如 \"A. $\\frac{1}{2}$\"，answer 填选项字母（A/B/C/D）",
    "blank": "全部为填空题：题干空位用 ____ 占位，answer 填简洁确定的结果（如 $1$、$\\frac{\\pi}{4}$、$y=Ce^x$）",
    "judge": "全部为判断题：statement 对或错各占一半，answer 填「对」或「错」，options 传空数组",
    "short": "全部为简答题（解答题）：题干提出需要推导/计算的问题，answer 给出分步参考解答"
             "（含关键步骤，数学用 LaTeX，80-200 字），analysis 概括解题关键与常见失分点",
}

PROMPT_HEAD = (
    "你是国内工科《高等数学》期末命题组老师，题目将直接进入在线题库。要求：\n"
    "1. 题目严谨、答案唯一确定，符合国内工科高数期末考试难度；难度分布约 easy 40% / medium 40% / hard 20%\n"
    "2. 【重要】所有数学记号必须写成 LaTeX 并用 $...$ 包裹（行内）或 $$...$$（独立公式），"
    "例如 $\\lim\\limits_{x \\to 0} \\frac{\\sin x}{x}$、$x^2$、$e^x$、$\\int_0^1 f(x)\\,dx$；"
    "严禁写成 x^2、lim(x→0)、sinx/2 之类的纯文本形式\n"
    "3. 题干中文表述自然完整；不与常见教材例题逐字雷同\n"
    "4. 每题附一句中文解析\n"
)


def call_llm(prompt: str) -> str:
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + KEY)
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def fix_escapes(s: str) -> str:
    r"""修复模型 JSON 里的非法反斜杠转义（\lim、\' 等），逐 run 按奇偶处理：
    - run 后跟合法转义字符（"\/bfnrt 或 \uXXXX）：原样保留（奇偶都合法）
    - run 后跟非法字符（如 x/l/s/'）：奇数个则补 1 个凑成偶数（偶数 = 字面反斜杠）
    - \' JSON 不允许：偶数个反斜杠 + 裸引号（LaTeX 的 f' 撇号意图）
    """
    out = []
    i, n = 0, len(s)
    while i < n:
        if s[i] != '\\':
            out.append(s[i])
            i += 1
            continue
        j = i
        while j < n and s[j] == '\\':
            j += 1
        k = j - i
        nxt = s[j] if j < n else ''
        valid_escape = nxt in ('"', '/', 'b', 'f', 'n', 'r', 't') or (
            nxt == 'u' and j + 5 <= n and all(ch in '0123456789abcdefABCDEF' for ch in s[j + 1:j + 5]))
        if nxt == "'":
            out.append('\\' * (k // 2 * 2))
            out.append("'")
            i = j + 1
        elif valid_escape or k % 2 == 0:
            out.append('\\' * k)
            i = j
        else:
            out.append('\\' * (k + 1))
            i = j
    return ''.join(out)


def parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        # json_object 模式可能返回 {"questions":[...]}，兜底取第一个 [ 到最后一个 ]
        start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    raw = fix_escapes(raw)
    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        raise
    if isinstance(data, dict):  # json_object 模式包裹层
        for v in data.values():
            if isinstance(v, list):
                return v
    return data


def validate(it: dict, qtype: str) -> bool:
    if not it.get("stem") or not it.get("answer"):
        return False
    opts = it.get("options") or []
    if qtype == "single":
        if len(opts) != 4 or not all(re.match(r"^[A-D]\. ", o) for o in opts):
            return False
        return it["answer"].strip().upper() in ("A", "B", "C", "D")
    if qtype == "judge":
        return it["answer"].strip() in ("对", "错") and not opts
    if qtype == "blank":
        return 0 < len(it["answer"].strip()) <= 40 and not opts
    if qtype == "short":
        return len(it["answer"].strip()) >= 20 and not opts
    return False


def norm_stem(s: str) -> str:
    return re.sub(r"[\s$]+", "", s or "")


def gen_group(kp: str, qtype: str, n: int) -> list:
    prompt = (
        f"{PROMPT_HEAD}\n"
        f"围绕知识点「{kp}」出 {n} 道题。{QTYPE_LINE[qtype]}\n"
        "只输出严格 JSON 数组，每个元素格式：\n"
        '[{"qtype":"' + qtype + '","stem":"题干","options":["A. ...","B. ...","C. ...","D. ..."],'
        '"answer":"...","analysis":"解析","difficulty":"easy|medium|hard"}]\n'
        "不要输出任何其他内容。"
    )
    for attempt in range(3):
        try:
            items = parse_json(call_llm(prompt))
            if isinstance(items, list):
                ok = []
                for it in items:
                    if it.get("qtype") != qtype:
                        continue
                    if not validate(it, qtype):
                        continue
                    it["knowledge_point"] = kp
                    it["qtype"] = qtype
                    d = it.get("difficulty", "medium")
                    it["difficulty"] = d if d in ("easy", "medium", "hard") else "medium"
                    ok.append(it)
                if len(ok) >= n * 0.5:
                    return ok[:n + 3]
        except Exception as e:
            print(f"  !! {kp}/{qtype} 第{attempt + 1}次失败: {str(e)[:100]}", flush=True)
        time.sleep(2)
    return []


def main():
    if not KEY:
        print("未配置 DEEPSEEK_KEY，退出")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    existing = {norm_stem(r[0]) for r in conn.execute(
        "SELECT stem FROM questions WHERE subject='math'").fetchall()}
    conn.close()
    print(f"库内现有数学题干指纹 {len(existing)} 条")

    groups = [(kp, qt, n) for kp, d in PLAN.items() for qt, n in d.items() if n > 0]
    print(f"生成任务 {len(groups)} 组，4 并发...")
    collected = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(gen_group, kp, qt, n): (kp, qt) for kp, qt, n in groups}
        for fut in cf.as_completed(futs):
            kp, qt = futs[fut]
            got = fut.result()
            collected.extend(got)
            print(f"  [{kp}/{qt}] 生成并通过校验 {len(got)} 题", flush=True)

    # 去重（对比库内 + 批内）
    conn = sqlite3.connect(DB_PATH)
    inserted, dup = 0, 0
    for it in collected:
        fp = norm_stem(it["stem"])
        if fp in existing:
            dup += 1
            continue
        existing.add(fp)
        conn.execute(
            "INSERT INTO questions (subject, knowledge_point, qtype, difficulty, stem, options, answer, analysis, source) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("math", it["knowledge_point"], it["qtype"], it["difficulty"], it["stem"],
             json.dumps(it.get("options", []), ensure_ascii=False), it["answer"], it.get("analysis", ""), "ai"))
        inserted += 1
    conn.commit()
    conn.close()
    print(f"\n完成：新增 {inserted} 题，去重丢弃 {dup} 题")
    for qt in ("single", "multiple", "judge", "blank", "short"):
        conn = sqlite3.connect(DB_PATH)
        c = conn.execute("SELECT count(*) FROM questions WHERE subject='math' AND qtype=?", (qt,)).fetchone()[0]
        conn.close()
        print(f"  math/{qt}: {c}")


if __name__ == "__main__":
    main()
