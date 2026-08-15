# -*- coding: utf-8 -*-
"""
用 DeepSeek 批量生成高等数学真题目（替换 demo 感），覆盖上下册核心知识点。

知识点(每点 N 道): 极限/导数/积分/多元函数/重积分/级数/微分方程
题型: 单选/判断/填空 混合, 题干支持 LaTeX, 每题带标准答案+解析。
插入 questions 表 subject=math, source='ai'。
用法: python generate_math_bank.py [--each 8]
"""
import argparse
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

POINTS = ["极限", "导数", "积分", "多元函数", "重积分", "级数", "微分方程"]


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


QTYPE_DESC = {
    "all": "题型合理搭配：单选(4个选项 A./B./C./D., 答案填字母)、判断(答案填\"对\"或\"错\")、填空(答案填确定文本如 \"1\" 或 \"x^2+C\")",
    "single": "全部为单选题(4个选项 A./B./C./D., 答案填选项字母，如 A)",
    "judge": "全部为判断题(答案填\"对\"或\"错\")，判断题 options 传空数组",
    "blank": "全部为填空题(答案填确定文本如 \"1\" 或 \"x^2+C\")，填空题 options 传空数组",
}
DIFFICULTY_DESC = {
    "easy": "全部为简单难度（easy），考查基本概念与直接计算",
    "medium": "全部为中等难度（medium），考查公式运用与常见套路",
    "hard": "全部为困难难度（hard），考查综合应用、多步推理、易错陷阱，避免送分题",
    "all": "",
}


def gen_for_point(kp: str, n: int, difficulty: str = "all", qtype: str = "all") -> list:
    qtype_line = QTYPE_DESC.get(qtype, QTYPE_DESC["all"])
    diff_line = DIFFICULTY_DESC.get(difficulty, "")
    prompt = (
        f"你是国内工科《高等数学》期末考试命题老师，围绕知识点「{kp}」出 {n} 道题。\n"
        "要求：\n"
        "- 题目严谨、答案确定，符合国内工科高数期末难度\n"
        "- 题干可用 LaTeX（如 $\\int_0^1 x\\,dx$、$\\lim_{x\\to0}\\frac{\\sin x}{x}$）\n"
        f"- {qtype_line}\n"
        f"- {diff_line}\n"
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
                    # 强制难度（避免 AI 自由发挥，保证按参数入库）
                    if difficulty in ("easy", "medium", "hard"):
                        for it in ok:
                            it["difficulty"] = difficulty
                    return ok
            print(f"  !! {kp} 解析条数不符({len(items)}), 重试")
        except Exception as e:
            print(f"  !! {kp} 生成失败: {str(e)[:120]}, 重试")
        time.sleep(2)
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--each", type=int, default=8, help="每个知识点生成道数")
    ap.add_argument("--difficulty", choices=["all", "easy", "medium", "hard"], default="all",
                    help="强制难度（hard 用于补齐难题）")
    ap.add_argument("--qtype", choices=["all", "single", "judge", "blank"], default="all",
                    help="限定题型")
    args = ap.parse_args()
    if not DEEPSEEK_KEY:
        print("未配置 DEEPSEEK_KEY，退出")
        sys.exit(1)

    conn = get_conn()
    total = 0
    for kp in POINTS:
        items = gen_for_point(kp, args.each, args.difficulty, args.qtype)
        created = 0
        for it in items:
            if args.qtype in ("single", "judge", "blank"):
                qtype = args.qtype
            else:
                qtype = it.get("qtype", "single")
            if qtype not in ("single", "multiple", "judge", "blank", "short"):
                qtype = "single"
            diff = it.get("difficulty", "medium")
            if diff not in ("easy", "medium", "hard"):
                diff = "medium"
            conn.execute(
                "INSERT INTO questions (subject, knowledge_point, qtype, difficulty, stem, options, answer, analysis, source) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("math", kp, qtype, diff, it["stem"],
                 json.dumps(it.get("options", []), ensure_ascii=False), it["answer"],
                 it.get("analysis", ""), "ai"))
            created += 1
        conn.commit()
        total += created
        print(f"[{kp}] 生成 {created} 题")
        time.sleep(1)
    conn.close()
    print(f"\n完成: 共新增 {total} 道数学题 (difficulty={args.difficulty}, qtype={args.qtype})")


if __name__ == "__main__":
    main()
