<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import 'katex/dist/katex.min.css'

// 模块级单例：markdown-it + katex 初始化开销不小，题库/知识库一页几十个组件
// 若放组件 setup 里会重复创建几十份实例；提到模块层全站共用一份
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

md.use(texmath, { engine: katex, delimiters: 'dollars', katexOptions: { throwOnError: false } })

const props = defineProps({
  content: {
    type: String,
    default: '',
  },
})

// ===== 裸文本数学包裹器 =====
// 把 AI 回复里"没被 $ 包裹"的数学记号自动包成 $...$ 交给 KaTeX 渲染，
// 例如：e^x → $e^x$、x_0 → $x_0$、\frac{1}{2} → $\frac{1}{2}$、x→0 → $x\to 0$
// 已存在的公式($ / $$)、代码块、行内代码、markdown 链接不会被误伤。
const MATH_CHAR = /[A-Za-z0-9+\-*/=<>()[\],.:;!'`^_{}\\|°±×÷≈≠≥≤→←↑↓∞∫∑∏√∂Δ∇παβγδεθλμνφψωΩ∈⊂⊆∪∩∀∃₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁻⁺]/
const MATH_MARKER = /[\^_\\∫∑∏√∞→←↑↓≠≈≥≤±×÷∂Δ∇παβγδεθλμνφψωΩ₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁻⁺]/
const UNI_TO_LATEX = {
  '→': '\\to', '←': '\\gets', '∞': '\\infty', '∑': '\\sum', '∫': '\\int', '∏': '\\prod',
  '×': '\\times', '÷': '\\div', '≠': '\\ne', '≥': '\\ge', '≤': '\\le', '≈': '\\approx',
  '±': '\\pm', '∂': '\\partial', 'π': '\\pi', 'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma',
  'δ': '\\delta', 'ε': '\\epsilon', 'θ': '\\theta', 'λ': '\\lambda', 'μ': '\\mu',
  'φ': '\\phi', 'ψ': '\\psi', 'ω': '\\omega', 'Δ': '\\Delta',
  '₀': '_0', '₁': '_1', '₂': '_2', '₃': '_3', '₄': '_4',
  '₅': '_5', '₆': '_6', '₇': '_7', '₈': '_8', '₉': '_9',
  '⁰': '^0', '¹': '^1', '²': '^2', '³': '^3', '⁴': '^4',
  '⁵': '^5', '⁶': '^6', '⁷': '^7', '⁸': '^8', '⁹': '^9',
  'ⁿ': '^n', '⁻': '^-', '⁺': '^+',
}

function isMathChar(ch) { return MATH_CHAR.test(ch) }

function needsMathWrap(tok) {
  if (!tok || tok.length > 24) return false
  // 填空占位下划线（如 ____）不是数学记号，直接显示避免 KaTeX 报错
  if (/^_+$/.test(tok)) return false
  return MATH_MARKER.test(tok)
}

function toLatex(tok) {
  let t = tok
  for (const k in UNI_TO_LATEX) t = t.split(k).join(UNI_TO_LATEX[k])
  return t
}

function wrapPlainMath(src) {
  const guards = []
  const guard = (m) => { guards.push(m); return '[[G]]' + (guards.length - 1) + '[[G]]' }
  // 先保护已有公式/代码/链接
  let s = (src || '')
    .replace(/\$\$[\s\S]*?\$\$/g, guard)
    .replace(/\$[^$\n]*?\$/g, guard)
    .replace(/```[\s\S]*?```/g, guard)
    .replace(/`[^`\n]*`/g, guard)
    .replace(/\[[^\]]*\]\([^)]*\)/g, guard)
  let out = ''
  let i = 0
  while (i < s.length) {
    const ch = s[i]
    if (s.startsWith('[[G]]', i)) {
      const j = s.indexOf('[[G]]', i + 5)
      out += guards[parseInt(s.slice(i + 5, j), 10)]
      i = j + 5
      continue
    }
    if (isMathChar(ch)) {
      // 扫描一个"数学片段"（追踪花括号，让 \frac{1}{2} 保持完整）
      let j = i
      let braces = 0
      while (j < s.length) {
        const c = s[j]
        if (c === '{') braces++
        if (c === '}') braces--
        if (braces < 0) break
        if (braces === 0 && !isMathChar(c)) break
        j++
      }
      const tok = s.slice(i, j)
      if (needsMathWrap(tok)) out += '$' + toLatex(tok) + '$'
      else out += tok
      i = j
      continue
    }
    out += ch
    i++
  }
  return out
}

// 统一两种公式格式为 dollars（markdown-it-texmath 的 dollars 模式支持 $ 和 $$）：
// - DeepSeek 回复用 \(...\) 和 \[...\] → 转成 $ 和 $$
// - 知识库内容本来就用 $...$ 和 $$...$$，保持不变
// - 模型偶发用单个 $ 包裹跨行公式（如 "$\n\n\lim...\n\n$"），
//   dollars 模式行内公式不跨空行会导致 LaTeX 源码直接暴露 → 统一转成块级 $$
function normalizeFormulas(src) {
  let s = src || ''
  // 块级 \[ \] → $$
  s = s.replace(/\\\[/g, '$$')
  s = s.replace(/\\\]/g, '$$')
  // 行内 \( \) → $
  s = s.replace(/\\\(/g, '$')
  s = s.replace(/\\\)/g, '$')
  // 扫描器：把"含换行的单 $...$"升级为块级 $$...$$，避免破坏已合法的 $/$ 对
  let out = ''
  let i = 0
  while (i < s.length) {
    if (s[i] !== '$') {
      out += s[i]
      i++
      continue
    }
    if (s[i + 1] === '$') {
      // 已是块级 $$...$$，原样复制到闭合 $$
      const end = s.indexOf('$$', i + 2)
      if (end === -1) {
        out += s.slice(i)
        break
      }
      out += s.slice(i, end + 2)
      i = end + 2
      continue
    }
    // 单个 $：向后找下一个单 $（跳过 $$ 块）
    let j = i + 1
    let found = -1
    while (j < s.length) {
      if (s[j] !== '$') {
        j++
        continue
      }
      if (s[j + 1] === '$') {
        j += 2
        continue
      }
      found = j
      break
    }
    if (found === -1) {
      out += s[i]
      i++
      continue
    }
    const inner = s.slice(i + 1, found)
    if (inner.includes('\n') || inner.includes('\r')) {
      out += '$$' + inner + '$$'
    } else {
      out += s.slice(i, found + 1)
    }
    i = found + 1
  }
  return out
}

const rendered = computed(() => md.render(wrapPlainMath(normalizeFormulas(props.content))))
</script>

<template>
  <div class="md-body" v-html="rendered"></div>
</template>

<style>
.md-body {
  font-size: 15px;
  line-height: 1.8;
  word-break: break-word;
}

.md-body h1,
.md-body h2,
.md-body h3,
.md-body h4 {
  margin: 0.8em 0 0.4em;
  line-height: 1.4;
}

.md-body h1 {
  font-size: 1.4em;
}

.md-body h2 {
  font-size: 1.25em;
}

.md-body h3 {
  font-size: 1.1em;
}

.md-body p {
  margin: 0.4em 0;
}

.md-body ul,
.md-body ol {
  padding-left: 1.5em;
  margin: 0.4em 0;
}

.md-body li {
  margin: 0.2em 0;
}

.md-body code {
  background: rgba(255, 255, 255, 0.10);
  border-radius: 4px;
  padding: 0.1em 0.4em;
  font-size: 0.92em;
  font-family: 'Consolas', 'Courier New', monospace;
}

.md-body pre {
  background: #0f172a;
  color: #e6e6e6;
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 8px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 0.6em 0;
}

.md-body pre code {
  background: transparent;
  color: inherit;
  padding: 0;
}

.md-body blockquote {
  border-left: 3px solid rgba(99, 102, 241, 0.6);
  padding-left: 12px;
  margin: 0.6em 0;
  color: #94a3b8;
}

.md-body table {
  border-collapse: collapse;
  margin: 0.6em 0;
  width: 100%;
}

.md-body th,
.md-body td {
  border: 1px solid rgba(255, 255, 255, 0.14);
  padding: 6px 12px;
  text-align: left;
}

.md-body th {
  background: rgba(255, 255, 255, 0.06);
}

.md-body .katex-display {
  margin: 0.6em 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 0;
}

.md-body a {
  color: #a5b4fc;
}
</style>
