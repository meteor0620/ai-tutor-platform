# -*- coding: utf-8 -*-
"""
把 cet4_bank_raw.json + 官方答案/参考译文 合并成最终四级题库(2026-08-09)

产出: cet4_bank_final.json, 结构:
  papers: [{source, paper_label, passage_key, label, passage, translation,
            questions: [{num, stem, options:[..], answer, analysis}]}]
  translations: [{source, paper_label, stem, answer, analysis}]
答案来源: 2024年6月(速查表官方) + 2025年12月(解析官方) + 2025年6月(人工校对)
解析/参考译文: DeepSeek 生成(附原文, 保证 grounded)
"""
import json
import os
import re
import sys
import time
import urllib.request

import fitz

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = "E:/AI教辅智学平台/英语四级"
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_KEY", "")  # 从 .env 读取
API = "https://api.deepseek.com/chat/completions"

# ---------------- 官方答案(46-55) ----------------
OFFICIAL = {
    "2024年6月/2024年06月大学英语四级考试真题（第1套）.pdf": "CBDADCBDAC",
    "2024年6月/2024年06月大学英语四级考试真题（第2套）.pdf": "BADCBDBACC",
    "2024年6月/2024年06月大学英语四级考试真题（第3套）.pdf": "CADBDACADB",
    "2025年6月/2025.06四级真题第1套.pdf": "DACBCACBDB",
    "2025年6月/2025.06四级真题第2套.pdf": "ADBDCADCBA",
    "2025年6月/2025.06四级真题第3套.pdf": "BCDACCABDA",
    "2025年12月/2025年12月四级真题第1套.pdf": "ACABAACDBD",
    "2025年12月/2025年12月四级真题第2套.pdf": "ADBCCDBACD",
    "2025年12月/2025年12月四级真题第3套.pdf": "ABACDADCBD",
}

# ---------------- 缺失题目补齐(双栏交错排版丢失) ----------------
PATCHED = {
    ("2025年6月/2025.06四级真题第1套.pdf", 51): {
        "stem": "What does the passage say about people born with natural talents?",
        "options": ["A) They seem to outdo others without hard work.",
                    "B) They appear to know all the secrets to success.",
                    "C) They feel it only too logical to succeed.",
                    "D) They are bound to excel effortlessly."],
    },
    ("2025年6月/2025.06四级真题第3套.pdf", 48): {
        "stem": "What does the author say about outer beauty?",
        "options": ["A) It may be inherited or cultivated.",
                    "B) It may lead to bad as well as good habits.",
                    "C) It may create connection or isolation.",
                    "D) It may do as much harm as good."],
    },
}


def call_deepseek(prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> str:
    payload = {"model": "deepseek-chat",
               "messages": [{"role": "user", "content": prompt}],
               "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(API, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + DEEPSEEK_KEY)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def gen_analyses(passage: str, qs: list) -> list:
    """一次调用生成一道passage全部题的简短中文解析(带答案, 保证 grounded)"""
    lines = []
    for q in qs:
        lines.append(
            f"Q{q['num']}: {q['stem']}\n"
            + "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(q["options"]))
            + f"\n答案: {q['answer']}")
    prompt = (
        "你是四级阅读解析老师。下面是一篇四级阅读文章和它对应的题目、选项、标准答案。\n"
        f"=====文章=====\n{passage}\n=====题目=====\n" + "\n\n".join(lines) +
        "\n\n请为每一题输出一句到两句中文解析(结合原文说明正确答案为什么对、干扰项错在哪)。"
        "只输出严格JSON数组，元素为字符串(每题一条)，不要输出任何其他内容，格式: [\"解析1\",\"解析2\",...]。"
    )
    for attempt in range(3):
        try:
            raw = call_deepseek(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
            arr = json.loads(raw)
            if isinstance(arr, list) and len(arr) == len(qs):
                return arr
            print("  !! 解析条数不符, 重试", len(arr), len(qs))
        except Exception as e:
            print("  !! 解析解析失败:", str(e)[:100], "重试")
        time.sleep(2)
    return [""] * len(qs)


def extract_official_translation(pdf: str) -> str:
    """从 2024年6月速查 PDF 提取官方参考译文"""
    d = fitz.open(pdf)
    full = "\n".join(d[i].get_text() for i in range(d.page_count))
    d.close()
    m = re.search(r"参考译文：\s*(.*?)\s*\Z", full, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def paper_label(src: str) -> str:
    folder = src.split("/")[0]
    m = re.search(r"第(\d)套", os.path.basename(src))
    return f"{folder} 第{m.group(1)}套" if m else folder


def main():
    raw = json.load(open(os.path.join(BASE, "cet4_bank_raw.json"), encoding="utf-8"))

    # 2024年6月 官方参考译文
    official_trans = {}
    for t in ["第1套", "第2套", "第3套"]:
        p = os.path.join(PDF_DIR, f"2024年6月/2024年06月四级考试真题答案速查（{t}）.pdf")
        official_trans[f"2024年6月 第{t}"] = extract_official_translation(p)

    papers_out, translations_out = [], []
    total_q = 0
    for r in raw:
        src = r["source"].replace("\\", "/")
        paper = paper_label(src)
        ans_seq = OFFICIAL.get(src, "")
        ans_map = {46 + i: ans_seq[i] for i in range(len(ans_seq))} if len(ans_seq) == 10 else {}

        for p in ["passage_one", "passage_two"]:
            if not r[p]:
                continue
            qs = r[p]["questions"]
            # 补齐缺失题目
            for (src_, num), patch in PATCHED.items():
                if src_ == src and num in range(46, 56) and num not in [q["num"] for q in qs] \
                        and (p == "passage_one") == (num <= 50):
                    qs.append({"num": num, "passage": p, "stem": patch["stem"], "options": patch["options"]})
            qs.sort(key=lambda x: x["num"])
            for q in qs:
                q["answer"] = ans_map.get(q["num"], "")
                if not q["answer"]:
                    print(f"  !! 无答案: {src} Q{q['num']}")
            # 生成解析
            anas = gen_analyses(r[p]["passage"], qs)
            for q, a in zip(qs, anas):
                q["analysis"] = a
            total_q += len(qs)
            papers_out.append({
                "source": src, "paper": paper, "passage_key": f"{paper}-{r[p]['label']}",
                "label": r[p]["label"], "passage": r[p]["passage"], "questions": qs,
            })
            print(f"[阅读] {paper} {r[p]['label']} {len(qs)}题 答案={[q['answer'] for q in qs]}")
            time.sleep(1)

        # 翻译
        if r.get("translation"):
            ref = official_trans.get(paper, "")
            if not ref:
                try:
                    ref = call_deepseek(
                        "请把下面这段中文翻译成地道英文(四级翻译参考译文风格，保持原文全部信息点)。\n" + r["translation"],
                        temperature=0.3, max_tokens=1024).strip()
                except Exception as e:
                    ref = ""
                    print("  !! 参考译文生成失败:", e)
                time.sleep(1)
            translations_out.append({
                "source": src, "paper": paper, "stem": r["translation"], "answer": ref,
            })
            print(f"[翻译] {paper} 参考译文={len(ref)}字")

    out = {"papers": papers_out, "translations": translations_out}
    path = os.path.join(BASE, "cet4_bank_final.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n完成: 阅读 {total_q} 题 / {len(papers_out)} 篇, 翻译 {len(translations_out)} 题")
    print("已写入:", path)


if __name__ == "__main__":
    main()
