# -*- coding: utf-8 -*-
"""
用 DeepSeek 扩充英语题型池：词汇/语法/写作（原 demo 池太小，替换为四级风格题）。

- 词汇: 20 道单选（四级核心词汇，词义辨析/搭配）
- 语法: 15 道（单选/判断混合，四级语法点：虚拟语气/定语从句/非谓语/时态）
- 写作: 10 道（判断/填空，写作技巧：句型/衔接/结构）
插入 questions 表 subject=english, source='ai'。
用法: python generate_english_pools.py
"""
import io
import json
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from config import get
from database import get_conn

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY = get("DEEPSEEK_KEY", "")

# 各题型: (知识点, 生成数量, 命题要求)
POOLS = [
    ("词汇", 20,
     "四级核心词汇单选题：给出一句含空格的英文句子，4个选项中只有一个词义最合适（考查词汇量/词义辨析/常见搭配）。答案填选项字母。"),
    ("语法", 15,
     "四级语法题，单选与判断混合：虚拟语气/定语从句/非谓语动词/时态语态/倒装强调等常见考点。单选给4个选项答案填字母，判断题干句子正误答案填\"对\"或\"错\"。"),
    ("写作", 10,
     "大学英语四级写作技巧题，判断与填空混合：考查衔接词用法、句型变换、段落结构、避免中式英语等写作方法。判断题答案填\"对\"或\"错\"，填空题答案填确定文本（如 \"However\"）。"),
]


def call_deepseek(prompt: str, temperature: float = 0.6, max_tokens: int = 8192) -> str:
    payload = {"model": "deepseek-chat",
               "messages": [{"role": "user", "content": prompt}],
               "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(DEEPSEEK_API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + DEEPSEEK_KEY)
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("["), raw.rfind("]")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    return json.loads(raw)


def gen_for_pool(kp: str, n: int, req_desc: str) -> list:
    prompt = (
        f"你是大学英语四级命题老师，围绕「{kp}」出 {n} 道题。\n"
        f"命题要求：{req_desc}\n"
        "- 题目严谨、答案确定\n"
        "- 单选题4个选项 A./B./C./D.，答案填选项字母\n"
        "- 判断题答案填\"对\"或\"错\"，填空题答案填确定文本\n"
        "- 每题附一句中文解析\n"
        "只输出严格 JSON 数组，格式：\n"
        '[{"qtype":"single","stem":"题干","options":["A. ...","B. ...","C. ...","D. ..."],"answer":"A","analysis":"解析","difficulty":"easy|medium|hard"}]'
        "\n判断题/填空题 options 传空数组。不要输出任何其他内容。"
    )
    for attempt in range(3):
        try:
            raw = call_deepseek(prompt)
            items = parse_json(raw)
            if isinstance(items, list) and items:
                ok = [it for it in items if it.get("stem") and it.get("answer")]
                if len(ok) >= n * 0.6:
                    return ok
            print(f"  !! {kp} 条数不符({len(items)}), 重试")
        except Exception as e:
            print(f"  !! {kp} 生成失败: {str(e)[:120]}, 重试")
        time.sleep(2)
    return []


def main():
    if not DEEPSEEK_KEY:
        print("未配置 DEEPSEEK_KEY，退出")
        sys.exit(1)

    conn = get_conn()
    total = 0
    for kp, n, req_desc in POOLS:
        items = gen_for_pool(kp, n, req_desc)
        created = 0
        for it in items:
            qtype = it.get("qtype", "single")
            if qtype not in ("single", "multiple", "judge", "blank", "short"):
                qtype = "single"
            diff = it.get("difficulty", "medium")
            if diff not in ("easy", "medium", "hard"):
                diff = "medium"
            conn.execute(
                "INSERT INTO questions (subject, knowledge_point, qtype, difficulty, stem, options, answer, analysis, source) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("english", kp, qtype, diff, it["stem"],
                 json.dumps(it.get("options", []), ensure_ascii=False), it["answer"],
                 it.get("analysis", ""), "ai"))
            created += 1
        conn.commit()
        total += created
        print(f"[{kp}] 生成 {created} 题")
        time.sleep(1)
    conn.close()
    print(f"\n完成: 共新增 {total} 道英语题")


if __name__ == "__main__":
    main()
