# -*- coding: utf-8 -*-
"""
数学库文档升级：LaTeX 笔记 -> 纯文本 + 细粒度分段（~900字/段）
删除旧的「高等数学微积分完整笔记」文档，替换为预处理后的版本（KB 不变）。
"""
import io
import json
import re
import sys
import time

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from config import get

BASE = get("MAXKB_BASE", "http://localhost:8080").rstrip("/")
ids = json.load(open("rebuild_ids.json", encoding="utf-8"))
KB = ids["math_kb"]
OLD_DOC_NAME = "高等数学微积分完整笔记"
SRC = r"..\素材\微积分LaTeX\高等数学微积分完整笔记.md"
MAX_CHARS = 900

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = [
    ("\\infty", "∞"), ("\\cdot", "·"), ("\\cdots", "…"), ("\\ldots", "…"), ("\\vdots", "⋮"),
    ("\\dots", "…"), ("\\times", "×"), ("\\div", "÷"), ("\\pm", "±"), ("\\mp", "∓"),
    ("\\leqslant", "≤"), ("\\geqslant", "≥"),
    ("\\leq", "≤"), ("\\le", "≤"), ("\\geq", "≥"), ("\\ge", "≥"), ("\\neq", "≠"), ("\\ne", "≠"),
    ("\\approx", "≈"), ("\\equiv", "≡"), ("\\sim", "~"), ("\\propto", "∝"),
    ("\\rightarrow", "→"), ("\\to", "→"), ("\\leftarrow", "←"), ("\\Rightarrow", "⇒"),
    ("\\longrightarrow", "⟶"), ("\\Longrightarrow", "⟹"), ("\\Leftrightarrow", "⇔"),
    ("\\leftrightarrow", "↔"), ("\\mapsto", "↦"), ("\\nRightarrow", "⇏"),
    ("\\subseteq", "⊆"), ("\\subset", "⊂"), ("\\supseteq", "⊇"), ("\\supset", "⊃"),
    ("\\cup", "∪"), ("\\cap", "∩"), ("\\emptyset", "∅"), ("\\varnothing", "∅"),
    ("\\in", "∈"), ("\\notin", "∉"), ("\\ni", "∋"), ("\\forall", "∀"), ("\\exists", "∃"),
    ("\\neg", "¬"), ("\\lnot", "¬"), ("\\partial", "∂"), ("\\nabla", "∇"),
    ("\\sum", "Σ"), ("\\prod", "Π"), ("\\coprod", "∏"), ("\\int", "∫"), ("\\iint", "∬"),
    ("\\iiint", "∭"), ("\\oint", "∮"), ("\\bigcup", "∪"), ("\\bigcap", "∩"),
    ("\\limsup", "lim sup"), ("\\liminf", "lim inf"), ("\\log", "log"), ("\\ln", "ln"),
    ("\\sin", "sin"), ("\\cos", "cos"), ("\\tan", "tan"), ("\\cot", "cot"),
    ("\\sec", "sec"), ("\\csc", "csc"), ("\\arcsin", "arcsin"), ("\\arccos", "arccos"),
    ("\\arctan", "arctan"), ("\\max", "max"), ("\\min", "min"), ("\\exp", "exp"),
    ("\\det", "det"), ("\\dim", "dim"), ("\\arg", "arg"), ("\\gcd", "gcd"),
    ("\\deg", "deg"), ("\\sup", "sup"), ("\\inf", "inf"), ("\\lim", "lim"),
    ("\\prime", "′"), ("\\circ", "°"), ("\\bullet", "·"), ("\\star", "*"),
    ("\\langle", "⟨"), ("\\rangle", "⟩"), ("\\|", "‖"), ("\\mid", "|"),
    ("\\{", "{"), ("\\}", "}"), ("\\quad", "  "), ("\\qquad", "  "),
]

# 替换前先按命令长度降序排列：保证 \int 先于 \in、\left 先于 \le、
# \cdots 先于 \cdot、\leqslant 先于 \leq（否则短命令先替换会吃掉长命令的前缀）
SYMBOLS.sort(key=lambda kv: -len(kv[0]))


def _strip_size_cmds(s: str) -> str:
    r"""去掉 \big \Big \bigg \Bigg \left \right \limits \displaystyle 等排版修饰符（必须在符号替换前）"""
    s = re.sub(r"\\[Bb]igg?[Gg]?", "", s)
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\limits", "").replace("\\displaystyle", "")
    return s


def read_arg(s, i):
    r"""读第 i 个参数 \cmd{arg}，返回 (arg内容, 结束索引)；无花括号则取单字符"""
    while i < len(s) and s[i] in " \t\n":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] != "{":
        return s[i], i + 1
    depth, j = 1, i + 1
    while j < len(s) and depth:
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
        j += 1
    return s[i + 1:j - 1], j


def latex_to_text(s):
    r"""\frac{a}{b} -> (a/b)；\sqrt{x} -> √(x)；递归处理嵌套"""
    # 排版修饰符最先剥离，避免 \left/\Big 的残体混进后续替换
    s = _strip_size_cmds(s)
    # \frac / \dfrac / \tfrac {a}{b}
    pat = re.compile(r"\\[dt]?frac")
    while True:
        m = pat.search(s)
        if not m:
            break
        a, j = read_arg(s, m.end())
        b, k = read_arg(s, j)
        s = s[:m.start()] + f"({a})/({b})" + s[k:]
    # \binom{n}{k} -> C(n, k)
    pat = re.compile(r"\\binom")
    while True:
        m = pat.search(s)
        if not m:
            break
        a, j = read_arg(s, m.end())
        b, k = read_arg(s, j)
        s = s[:m.start()] + f"C({a}, {b})" + s[k:]
    # \sqrt[n]{x} / \sqrt{x}
    pat = re.compile(r"\\sqrt")
    while True:
        m = pat.search(s)
        if not m:
            break
        rest = s[m.end():]
        idx = ""
        if rest.startswith("["):
            e = rest.index("]")
            idx, rest = rest[1:e], rest[e + 1:]
        x, k = read_arg(s, m.end() + (len(idx) + 2 if idx else 0))
        p = f"({x})^(1/{idx})" if idx else f"√({x})"
        s = s[:m.start()] + p + s[k:]
    # \overline{x} \underline{x} \hat{x} \widetilde{x} \hat 等：保留内容
    for cmd in ("overline", "underline", "widehat", "widetilde", "hat", "tilde", "bar", "vec"):
        pat = re.compile(r"\\" + cmd)
        while True:
            m = pat.search(s)
            if not m:
                break
            a, k = read_arg(s, m.end())
            s = s[:m.start()] + a + s[k:]
    # \mathbb{R} \mathcal{F} \boldsymbol{x} \text{...} \operatorname{...}
    for cmd in ("mathbb", "mathcal", "mathbf", "mathfrak", "boldsymbol", "bm", "text", "mathrm",
                "mathit", "operatorname", "mbox", "textrm"):
        pat = re.compile(r"\\" + cmd)
        while True:
            m = pat.search(s)
            if not m:
                break
            a, k = read_arg(s, m.end())
            s = s[:m.start()] + a + s[k:]
    # \begin{xxx} \end{xxx}
    s = re.sub(r"\\(?:begin|end)\{[a-zA-Z*]+\}", "\n", s)
    # 希腊字母（长名优先，防止 \varepsilon 被 \epsilon 撞掉）
    for k in sorted(GREEK, key=len, reverse=True):
        s = s.replace("\\" + k, GREEK[k])
    # 符号与函数（已按长度降序，长命令先替换）
    for k, v in SYMBOLS:
        s = s.replace(k, v)
    # 上下标
    pat = re.compile(r"[\^_]")
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c in "^_":
            a, k = read_arg(s, i + 1)
            out.append(f"{c}({a})" if len(a) > 1 or a else a)
            i = k
        else:
            out.append(c)
            i += 1
    s = "".join(out)
    # 残余控制符
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("\\!", "").replace("\\,", " ").replace("\\;", " ").replace("\\:", " ")
    s = s.replace("\\ ", " ").replace("~", " ")
    s = s.replace("\\\\", "\n")
    s = s.replace("$", " ").replace(" & ", " ").replace("&", " ")
    # 残余花括号是 LaTeX 分组残留，转成圆括号（sin{x} -> sin(x)）
    s = s.replace("{", "(").replace("}", ")")
    return s


def clean_text(md):
    """整体清洗：数学块转文本 + 压缩空白"""
    md = latex_to_text(md)
    md = re.sub(r"[ \t]+", " ", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"^\s*>\s?", "", md, flags=re.M)  # 引用符
    return md.strip()


def chunk_md(md, max_chars=MAX_CHARS):
    """按标题层级切，段落合并到 ~max_chars；返回 [(title, content)]"""
    items, cur_title, buf = [], "", []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            items.append((cur_title, text))
        buf.clear()

    for line in md.splitlines():
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        if h:
            flush()
            cur_title = h.group(2).strip()
        else:
            buf.append(line)
    flush()

    paras = []
    for title, text in items:
        # 先按空行分段
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        cur = ""
        for b in blocks:
            if len(cur) + len(b) + 1 <= max_chars:
                cur = (cur + "\n" + b) if cur else b
                continue
            if cur:
                paras.append((title, cur))
            while len(b) > max_chars:  # 超长块按句子切
                cut = b.rfind("。", 0, max_chars)
                cut = cut if cut > max_chars // 2 else max_chars
                paras.append((title, b[:cut + 1].strip()))
                b = b[cut + 1:].strip()
            cur = b
        if cur:
            paras.append((title, cur))
    # 合并过碎的段
    merged = []
    for t, c in paras:
        if merged and len(c) < 60:
            mt, mc = merged[-1]
            if mt == t and len(mc) + len(c) <= max_chars + 60:
                merged[-1] = (mt, mc + "\n" + c)
                continue
        merged.append((t, c))
    return merged


def main():
    md = open(SRC, encoding="utf-8").read()
    print(f"源文件 {len(md)} 字符")
    clean = clean_text(md)
    paras = chunk_md(clean)
    print(f"清洗后 {len(clean)} 字符 -> {len(paras)} 段 (平均 {len(clean)//max(len(paras),1)} 字/段)")

    s = requests.Session()
    r = s.post(BASE + "/admin/api/user/login",
               json={"username": get("MAXKB_ADMIN", "admin"), "password": get("MAXKB_PASSWORD", ""),
                     "current_role": "ADMIN"}, timeout=30)
    s.headers["Authorization"] = "Bearer " + r.json()["data"]["token"]

    # 找旧文档
    docs = s.get(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document",
                 params={"page_size": 100}, timeout=30).json()["data"]
    old = [d for d in docs if d["name"] == OLD_DOC_NAME]
    if old:
        doc_id = old[0]["id"]
        r = s.delete(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document/{doc_id}", timeout=60)
        print(f"删除旧文档 {doc_id}: {r.json().get('code')}")
        time.sleep(3)

    payload = [{"name": OLD_DOC_NAME,
                "paragraphs": [{"title": t, "content": c, "is_active": True} for t, c in paras]}]
    r = s.put(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document/batch_create",
              json=payload, timeout=300)
    j = r.json()
    if j.get("code") != 200:
        raise RuntimeError(f"batch_create 失败: {str(j)[:400]}")
    new_id = j["data"][0]["id"]
    print(f"新文档已创建: {new_id}, {len(paras)} 段, 等待向量化...")

    for _ in range(60):
        time.sleep(15)
        docs = s.get(BASE + f"/admin/api/workspace/default/knowledge/{KB}/document",
                     params={"page_size": 100}, timeout=30).json()["data"]
        d = [x for x in docs if x["id"] == new_id][0]
        st, pc = str(d["status"]), d.get("paragraph_count", 0)
        print(f"  status={st} paragraphs={pc}/{len(paras)}", flush=True)
        if st.endswith("2") and pc == len(paras):
            print("向量化完成")
            break


if __name__ == "__main__":
    main()
