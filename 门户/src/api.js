import { SUBJECTS, getSubject } from './subjects'

// ============ 统一 API 层 ============
// full  模式：本机 FastAPI 后端 + MaxKB（开发/演示完整版）
// demo  模式：纯静态 JSON + 前端判卷 + Worker 代理 LLM（GitHub Pages 公网版）
// App.vue / Teacher.vue 只调这里，不感知模式差异。
export const isDemo = import.meta.env.VITE_DEMO === '1'
const BASE = import.meta.env.BASE_URL || '/'
const LLM_PROXY = (import.meta.env.VITE_LLM_PROXY || '').replace(/\/$/, '')

const cache = {}
function loadJson(name) {
  if (!cache[name]) cache[name] = fetch(`${BASE}demo/${name}.json`).then(r => r.json())
  return cache[name]
}

async function j(url, opt) {
  const res = await fetch(url, opt)
  return res.json()
}

// ============ 简易关键词检索（demo 版 RAG 检索） ============
const STOP = new Set('什么怎么怎样为什么是否还是还是如何这个那个哪些哪些以及或者但是因为所以如果虽然因此然后就是不是没有可以还有'.split('').concat(['什么', '怎么', '怎样', '为什么', '如何', '哪些', '哪些', '请问', '一下', '有关', '相关', '解释', '说明', '介绍', '讲述']))
function extractTerms(q) {
  const terms = new Set()
  for (const w of (q.toLowerCase().match(/[a-z]{3,}/g) || [])) terms.add(w)
  for (const seg of (q.replace(/[^\u4e00-\u9fff]+/g, ' ').split(/\s+/))) {
    if (!seg) continue
    if (seg.length <= 3 && !STOP.has(seg)) terms.add(seg)
    for (let i = 0; i + 2 <= seg.length; i++) {
      const g = seg.slice(i, i + 2)
      if (!STOP.has(g)) terms.add(g)
    }
  }
  return [...terms]
}

function scoreParagraph(para, terms, docName) {
  let s = 0
  const content = (para.title + ' ' + para.content).toLowerCase()
  const titleHit = terms.filter(t => (para.title || '').toLowerCase().includes(t)).length
  for (const t of terms) {
    if (t.length < 2) continue
    let c = 0, idx = 0
    while ((idx = content.indexOf(t, idx)) !== -1 && c < 8) { c++; idx += t.length }
    if (c) s += Math.min(c, 5) * (t.length >= 3 ? 2.2 : 1) + titleHit * 1.5
  }
  return s
}

function retrieve(kbDocs, query, topN = 6) {
  const terms = extractTerms(query)
  if (!terms.length) return []
  const hits = []
  for (const doc of kbDocs) {
    for (const p of doc.paragraphs) {
      const s = scoreParagraph(p, terms, doc.name)
      if (s > 0) hits.push({ doc: doc.name, para: p, s })
    }
  }
  hits.sort((a, b) => b.s - a.s)
  const max = hits[0]?.s || 1
  return hits.slice(0, topN).map(h => ({
    title: h.para.title || '',
    content: h.para.content,
    document_name: h.doc,
    similarity: Math.min(0.99, Math.round((h.s / max) * 100) / 100),
  }))
}

// ============ LLM（demo 模式经 Worker 代理，key 不落地前端） ============
async function llmChat(messages, temperature = 0.4) {
  if (!LLM_PROXY) throw new Error('未配置 LLM 代理')
  const res = await fetch(LLM_PROXY + '/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, temperature }),
  })
  if (!res.ok) throw new Error('LLM 代理返回 ' + res.status)
  const d = await res.json()
  return d.content || ''
}

// demo 模式各科目 LLM 提示词见 subjects.js 的 chatPrompt（单一事实源）

// ============ demo 数据加载 ============
async function demoQuestions(sub) { return loadJson('questions_' + sub) }
async function demoKb(sub) { return loadJson('kb_' + sub) }

// demo 内存卷：paperId -> questions
const demoPapers = {}
let demoPaperSeq = 1

function shuffle(arr) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function gradeObjective(q, ans) {
  const std = String(q.answer || '').trim().toUpperCase().replace(/\s+/g, '')
  const stu = String(ans || '').trim().toUpperCase().replace(/\s+/g, '')
  if (!stu) return false
  if (q.qtype === 'multiple') {
    return [...std].sort().join('') === [...stu].sort().join('')
  }
  if (q.qtype === 'judge') {
    const norm = v => ({ '对': '对', '正确': '对', 'T': '对', 'TRUE': '对', '√': '对', '错': '错', '错误': '错', 'F': '错', 'FALSE': '错', 'X': '错' }[v] || v)
    return norm(std) === norm(stu)
  }
  if (q.qtype === 'blank') {
    if (std === stu) return true
    const fStd = parseFloat(std), fStu = parseFloat(stu)
    if (!isNaN(fStd) && !isNaN(fStu)) return Math.abs(fStd - fStu) < 1e-6
    return stu.includes(std) || std.includes(stu)
  }
  return std === stu
}

// ============ 对外 API ============
export const api = {
  isDemo,

  // ---- 首页统计 ----
  async stats() {
    if (!isDemo) return j('/api/questions/stats')
    const items = {}
    for (const s of SUBJECTS) {
      const qs = await demoQuestions(s.id)
      items[s.id] = { total: qs.length }
    }
    return { code: 200, items }
  },

  async kbParagraphCount(sub) {
    const kb = await demoKb(sub)
    return kb.reduce((n, d) => n + d.paragraphs.length, 0)
  },

  // ---- 知识库 ----
  async knowledgeDocuments(sub) {
    if (!isDemo) return j(`/api/knowledge/${sub}/documents`)
    const kb = await demoKb(sub)
    return {
      code: 200,
      items: kb.map((d, i) => ({ id: 'd' + i, name: d.name, paragraph_count: d.paragraphs.length, status: 'ok' })),
    }
  },

  async knowledgeSections(sub, docId) {
    if (!isDemo) return j(`/api/knowledge/${sub}/documents/${docId}/sections`)
    const kb = await demoKb(sub)
    const doc = kb[Number(docId.slice(1))] || { paragraphs: [] }
    return {
      code: 200, total: doc.paragraphs.length,
      items: doc.paragraphs.map((p, i) => ({ id: 's' + i, title: p.title, content: p.content })),
    }
  },

  async knowledgeSearch(sub, query, topN = 6) {
    if (!isDemo) {
      return j(`/api/knowledge/${sub}/search`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: sub, query, top_n: topN }),
      })
    }
    const kb = await demoKb(sub)
    const hits = retrieve(kb, query, topN)
    return { code: 200, query, items: hits }
  },

  // ---- 组卷 / 判卷 ----
  async createPaper(payload) {
    if (!isDemo) return j('/api/papers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const sub = payload.subject
    const bank = await demoQuestions(sub)
    let picked = []
    const counts = payload.counts || {}
    for (const [qtype, n] of Object.entries(counts)) {
      const pool = bank.filter(q => q.qtype === qtype && (!q.passage || !payload.passages))
      picked = picked.concat(shuffle(pool).slice(0, n))
    }
    // 阅读理解：按篇抽取
    const np = payload.passages || 0
    if (np > 0) {
      const byKey = {}
      for (const q of bank) {
        if (q.passage && q.qtype === 'single') {
          if (!byKey[q.passage_key]) byKey[q.passage_key] = []
          byKey[q.passage_key].push(q)
        }
      }
      const keys = shuffle(Object.keys(byKey)).slice(0, np)
      for (const k of keys) picked = picked.concat(byKey[k])
    }
    // 知识点配置（英语自测面板）：按知识点抽；「阅读」按篇抽
    for (const [kp, n] of Object.entries(payload.knowledge_points || {})) {
      if (kp.includes('阅读')) {
        const byKey = {}
        for (const q of bank) {
          if (q.passage && !picked.some(x => x.passage_key === q.passage_key)) {
            if (!byKey[q.passage_key]) byKey[q.passage_key] = []
            byKey[q.passage_key].push(q)
          }
        }
        const keys = shuffle(Object.keys(byKey)).slice(0, n)
        for (const k of keys) picked = picked.concat(byKey[k].map(q => ({ ...q, options: q.options ? JSON.parse(q.options) : null })))
        continue
      }
      const need = Math.max(0, n - picked.filter(q => q.knowledge_point === kp).length)
      const pool = bank.filter(q => q.knowledge_point === kp && !picked.includes(q))
      picked = picked.concat(shuffle(pool).slice(0, need))
    }
    picked = picked.map(q => ({ ...q, options: q.options ? JSON.parse(q.options) : null }))
    const paperId = 'demo' + (demoPaperSeq++)
    demoPapers[paperId] = picked
    return { code: 200, paper_id: paperId, title: payload.title || '演示组卷', question_count: picked.length }
  },

  async getPaper(paperId) {
    if (!isDemo) return j(`/api/papers/${paperId}`)
    return { questions: demoPapers[paperId] || [] }
  },

  async submitPaper(paperId, { answers }) {
    if (!isDemo) return j(`/api/papers/${paperId}/submit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_id: paperId, answers }),
    })
    const questions = demoPapers[paperId] || []
    const results = {}
    let score = 0, total = 0
    const per = questions.length ? 100 / questions.length : 0
    for (const q of questions) {
      total += 1
      const stu = answers[q.id] || ''
      if (q.qtype === 'short') {
        // 简答题：有代理则 AI 评分，否则标记复核
        let aiScore = null, analysis = ''
        if (LLM_PROXY) {
          try {
            const out = await llmChat([
              { role: 'system', content: '你是严格的阅卷老师。给学生的简答题答案打分（0-10分整数），并给一句话点评。只输出JSON：{"score":数字,"comment":"..."}' },
              { role: 'user', content: `题目：${q.stem}\n参考答案：${q.answer}\n学生答案：${stu || '（未作答）'}` },
            ], 0.2)
            const m = out.match(/\{[\s\S]*\}/)
            const parsed = m ? JSON.parse(m[0]) : null
            if (parsed && typeof parsed.score === 'number') {
              aiScore = parsed.score / 10
              analysis = parsed.comment || ''
            }
          } catch (e) { /* fallthrough */ }
        }
        const ok = aiScore !== null ? aiScore >= 0.6 : false
        results[q.id] = {
          correct: ok, score: aiScore !== null ? Math.round(aiScore * per) : 0,
          student_answer: stu, std_answer: q.answer || '', analysis,
          needs_review: aiScore === null,
        }
        score += aiScore !== null ? Math.round(aiScore * per) : 0
      } else {
        const ok = gradeObjective(q, stu)
        if (ok) score += Math.round(per)
        results[q.id] = { correct: ok, student_answer: stu, std_answer: q.answer || '', analysis: q.analysis || '' }
      }
    }
    return { score, total: 100, results }
  },

  async reviewPaper({ student_name, subject }) {
    if (!isDemo) {
      const res = await fetch('/api/papers/review', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_name: student_name || '学生', subject }),
      })
      const data = await res.json()
      if (!res.ok || (data.code && data.code !== 200)) {
        const d = data.detail
        const msg = typeof d === 'string' ? d
          : Array.isArray(d) ? d.map(x => x.msg || x.message).join('；')
          : (d ? JSON.stringify(d) : '重练组卷失败')
        throw new Error(msg)
      }
      return data
    }
    // demo：从本地错题的知识点出发组一份巩固卷
    const { loadWrongData } = await import('./storage')
    const local = await loadWrongData()
    const kps = [...new Set(local.entries.filter(e => !e.mastered && e.subject === subject).map(e => e.knowledge_point).filter(Boolean))]
    if (!kps.length) return { code: 500, detail: '暂无待巩固的知识点' }
    const bank = await demoQuestions(subject)
    const picked = []
    for (const kp of shuffle(kps)) {
      const q = shuffle(bank.filter(x => x.knowledge_point === kp && !picked.includes(x)))[0]
      if (q) picked.push({ ...q, options: q.options ? JSON.parse(q.options) : null })
      if (picked.length >= 5) break
    }
    if (!picked.length) return { code: 500, detail: '题库暂无匹配题目' }
    const paperId = 'demo' + (demoPaperSeq++)
    demoPapers[paperId] = picked
    return { code: 200, paper_id: paperId, title: '错题巩固卷', question_count: picked.length }
  },

  async assignPapers(sub) {
    if (!isDemo) return j(`/api/papers?source=teacher&subject=${sub}`)
    return { code: 200, items: [] } // 公网演示版无教师布置卷
  },

  // ---- 错题本 ----
  async wrongBook(studentName) {
    if (!isDemo) return j(`/api/wrong-book?student_name=${encodeURIComponent(studentName)}`)
    const { loadWrongData } = await import('./storage')
    const local = await loadWrongData()
    return { code: 200, items: local.entries.map(e => ({ ...e, demo: false })) }
  },

  // ---- AI 答疑 ----
  async chatSend(subjectId, question, history) {
    if (!isDemo) {
      // 完整版：走 MaxKB 匿名链路（由 App.vue 原逻辑处理，这里不使用）
      throw new Error('full 模式请走原 chat 链路')
    }
    const kb = await demoKb(subjectId)
    const hits = retrieve(kb, question, 6)
    const data = hits.map(h => `【${h.title || h.document_name}】\n${h.content}`).join('\n\n')
    const p = getSubject(subjectId).chatPrompt
    const messages = [
      { role: 'system', content: p.system },
      ...history.slice(-6).map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content })),
      { role: 'user', content: p.prefix.replace('{question}', question).replace('{data}', data || '（未检索到相关内容）') },
    ]
    return { content: await llmChat(messages), references: hits }
  },

  hasLlmProxy: () => !!LLM_PROXY,
}
