# -*- coding: utf-8 -*-
"""
从四级真题 PDF 抽取 Part III Section C 阅读单选(46-55) 与 Part IV 翻译段落(2026-08-09)

用法: python extract_cet4.py [pdf目录]
输出: 同级目录 cet4_bank_raw.json, 每条含 passage_one/passage_two/translation
可选: --answers <解析目录> 尝试从解析PDF抽答案(未实现,答案由人工校对)
"""
import argparse
import glob
import io
import json
import os
import re
import sys

import fitz

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 常见 kerning/字距 OCR 瑕疵修正(部分真题PDF字距过紧导致字母粘连)
FIX = {
    "fbr": "for", "fiom": "from", "fbom": "from", "f^om": "from",
    "thafs": "that's", "Ifs": "It's", "ifs": "it's", "Fm": "I'm",
    "Fve": "I've", "o f": "of", "i f": "if", "re sults": "results",
    "a n d": "and", "fa mily": "family", "fiear": "hear",
}


def fix_text(s: str) -> str:
    for k, v in FIX.items():
        s = s.replace(k, v)
    return s


def normalize_space(s: str) -> str:
    """把换行/多空格压成单空格, 方便阅读题文章展示"""
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", " ", s)).strip()


def extract_pdf(pdf: str) -> dict:
    doc = fitz.open(pdf)
    full = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    full = full.replace("　", " ")

    # ---------- 1. 阅读 Section C ----------
    start = full.find("Passage One")
    t_end = full.find("Translation")
    if t_end < 0:
        t_end = full.find("Part IV")
    if t_end < 0:
        t_end = len(full)
    if start < 0 or start >= t_end:
        return None  # 该PDF无可用阅读区(扫描件等)

    sec_c = full[start:t_end]
    # 按 Passage 分块
    p1m = re.search(r"Passage\s+One\b", sec_c)
    p2m = re.search(r"Passage\s+Two\b", sec_c)
    if not p1m:
        return None
    p1_txt = p2m.start() if p2m else len(sec_c)
    p2_txt = len(sec_c) if p2m else None

    def parse_passage(body: str, label: str):
        # 去掉 "Questions 46 to 50 are based on the following passage."
        body = re.sub(r"Questions\s+\d+\s+to\s+\d+\s+are based on the following passage\.?\s*", "", body)
        # 问题块
        blocks = list(re.finditer(r"(?m)^\s*(\d{2})\s*\.\s*", body))
        if not blocks:
            return None
        # 文章 = 从body开头到第一个问题号
        passage = fix_text(normalize_space(body[:blocks[0].start()]))
        questions = []
        for bi, b in enumerate(blocks):
            num = int(b.group(1))
            if num < 46 or num > 55:
                continue
            seg = body[b.end():blocks[bi + 1].start() if bi + 1 < len(blocks) else len(body)]
            # 选项按字母收集: 全段扫描所有 X) 标记(兼容同行 A)..C).. 与换行交错排版)
            opt_ms = list(re.finditer(r"([A-D])\s*\)\s*", seg))
            opts = {}
            for oi, om in enumerate(opt_ms):
                letter = om.group(1)
                txt = seg[om.end():opt_ms[oi + 1].start() if oi + 1 < len(opt_ms) else len(seg)]
                opts[letter] = fix_text(normalize_space(txt))
            if len(opts) != 4:
                continue  # 不完整选项跳过
            stem = seg[:opt_ms[0].start()] if opt_ms else seg
            stem = fix_text(normalize_space(stem))
            questions.append({
                "num": num, "passage": label, "stem": stem,
                "options": [opts[k] for k in "ABCD"],
            })
        return {"label": label, "passage": passage, "questions": questions}

    p1 = parse_passage(sec_c[p1m.start():p1_txt], "Passage One")
    p2 = parse_passage(sec_c[p2m.start():p2_txt], "Passage Two") if p2m else None

    # ---------- 2. 翻译 ----------
    trans = None
    if t_end < len(full):
        tseg = full[t_end:]
        # 去掉方向说明, 取中文段落
        tseg = re.sub(r"^.*?Answer Sheet 2\.?\s*", "", tseg, flags=re.S)
        lines = []
        for ln in tseg.split("\n"):
            s = ln.strip()
            if not s:
                continue
            # 去掉页脚水印/公众号/页码
            if re.match(r"^\d{1,3}$", s):
                continue
            if "公众号" in s or "研池大叔" in s or "免费分享" in s:
                continue
            lines.append(s)
        if lines:
            trans = fix_text("\n".join(lines))

    # 过滤掉没有读到有效文章或题目的
    ok_q = (p1["questions"] if p1 else []) + (p2["questions"] if p2 else [])
    if not ok_q and not trans:
        return None
    return {"passage_one": p1, "passage_two": p2, "translation": trans}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="E:/AI教辅智学平台/英语四级")
    ap.add_argument("--folders", default="2024年6月,2025年6月,2025年12月")
    args = ap.parse_args()

    folders = [f.strip() for f in args.folders.split(",") if f.strip()]
    pdfs = []
    for f in folders:
        for p in sorted(glob.glob(os.path.join(args.dir, f, "**/*.pdf"), recursive=True)):
            b = os.path.basename(p)
            if "解析" in b or "速查" in b or "答案" in b:
                continue
            pdfs.append(p)

    results, failed = [], []
    for p in pdfs:
        rel = os.path.relpath(p, args.dir)
        try:
            r = extract_pdf(p)
            if r is None:
                failed.append((rel, "无可解析阅读区"))
                continue
            qs = (r["passage_one"]["questions"] if r["passage_one"] else []) + \
                 (r["passage_two"]["questions"] if r["passage_two"] else [])
            r["source"] = rel
            results.append(r)
            print(f"[OK] {rel}  阅读题={len(qs)}  翻译={'有' if r['translation'] else '无'}")
        except Exception as e:
            failed.append((rel, str(e)[:80]))

    print(f"\n共 {len(results)} 套成功, {len(failed)} 套失败")
    for rel, why in failed:
        print(f"  [X] {rel}: {why}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cet4_bank_raw.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写入:", out)


if __name__ == "__main__":
    main()
