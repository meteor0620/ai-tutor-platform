<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps({
  content: {
    type: String,
    default: '',
  },
})

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

md.use(texmath, { engine: katex, delimiters: 'dollars', katexOptions: { throwOnError: false } })

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

const rendered = computed(() => md.render(normalizeFormulas(props.content)))
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
  background: #eef0f4;
  border-radius: 4px;
  padding: 0.1em 0.4em;
  font-size: 0.92em;
  font-family: 'Consolas', 'Courier New', monospace;
}

.md-body pre {
  background: #282c34;
  color: #e6e6e6;
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
  border-left: 3px solid #cbd5e1;
  padding-left: 12px;
  margin: 0.6em 0;
  color: #64748b;
}

.md-body table {
  border-collapse: collapse;
  margin: 0.6em 0;
  width: 100%;
}

.md-body th,
.md-body td {
  border: 1px solid #e2e8f0;
  padding: 6px 12px;
  text-align: left;
}

.md-body th {
  background: #f1f5f9;
}

.md-body .katex-display {
  margin: 0.6em 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 0;
}

.md-body a {
  color: #4f46e5;
}
</style>
