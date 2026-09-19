<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { darkTheme } from 'naive-ui'
import { themeOverrides } from './theme'
import { message } from './naive'
import MarkdownRender from './components/MarkdownRender.vue'
import AppIcon from './components/AppIcon.vue'
import Teacher from './components/Teacher.vue'
import Mascot from './components/Mascot.vue'
import {
  loadChatSessions, saveChatSession, deleteChatSession, clearChatSessions,
  loadWrongData, saveWrongData,
} from './storage'
import { api, isDemo } from './api'
import { SUBJECTS, getSubject } from './subjects'

const subjects = SUBJECTS

const typeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', blank: '填空题', short: '简答题' }

// 首页统计（按科目 id 动态聚合，加科目自动纳入）
const bankStats = ref({})
const kbParas = ref({})
const sumOf = obj => Object.values(obj || {}).reduce((a, b) => a + (b || 0), 0)

// 导航状态: home | chat | quiz | wrong | kb
const view = ref('home')
const activeSubject = ref(null)
const quizSubject = ref(null)

// ============ 知识库 ============
const kbSubject = ref(null)
const kbDocs = ref([])
const kbSections = ref([])
const kbCurrentDoc = ref(null)
const kbCurrentSection = ref(null)
const kbSearchQuery = ref('')
const kbResults = ref([])
const kbSearching = ref(false)
const kbLoading = ref(false)
const kbError = ref('')

function docDisplayName(name) {
  return (name || '').replace(/^微积分(?:笔记)?-\d+-/, '')
}

async function openKnowledge(subject) {
  kbSubject.value = subject
  view.value = 'kb'
  kbDocs.value = []
  kbSections.value = []
  kbCurrentDoc.value = null
  kbCurrentSection.value = null
  kbResults.value = []
  kbSearchQuery.value = ''
  kbError.value = ''
  kbLoading.value = true
  try {
    const data = await api.knowledgeDocuments(subject.id)
    if (data.code && data.code !== 200) throw new Error(data.message || '加载失败')
    kbDocs.value = data.items || []
    if (kbDocs.value.length) openDoc(kbDocs.value[0])
  } catch (e) {
    kbError.value = '知识库加载失败：' + (e.message || '请确认后端服务已启动')
  } finally {
    kbLoading.value = false
  }
}

async function openDoc(doc) {
  kbCurrentDoc.value = doc
  kbSections.value = []
  kbCurrentSection.value = null
  kbResults.value = []
  kbError.value = ''
  try {
    const data = await api.knowledgeSections(kbSubject.value.id, doc.id)
    if (data.code && data.code !== 200) throw new Error(data.message || '加载失败')
    kbSections.value = data.items || []
    if (kbSections.value.length) {
      kbCurrentSection.value = kbSections.value[0]
    }
  } catch (e) {
    kbError.value = '章节加载失败：' + (e.message || '请稍后重试')
  }
}

function selectSection(sec) {
  kbCurrentSection.value = sec
}

async function kbSearch() {
  const q = kbSearchQuery.value.trim()
  if (!q) return
  kbSearching.value = true
  kbError.value = ''
  try {
    const data = await api.knowledgeSearch(kbSubject.value.id, q, 5)
    if (data.code && data.code !== 200) throw new Error(data.message || '检索失败')
    kbResults.value = data.items || []
  } catch (e) {
    kbResults.value = []
    kbError.value = '检索失败：' + (e.message || '请稍后重试')
  } finally {
    kbSearching.value = false
  }
}

// ============ 对话 ============
const chatToken = ref('')
const chatId = ref('')
const messages = ref([])
const input = ref('')
const chatLoading = ref(false)
// ---- 聊天记录（本地专属存储，将来换服务端按账号存） ----
const chatSessions = ref([])
const showHistory = ref(false)
const currentSession = ref(null) // {id, title, time, messages}

// ============ 自测 ============
const quizQuestions = ref([])
const quizAnswers = ref({})
const quizResult = ref(null)
const quizLoading = ref(false)
const quizMode = ref('')
const quizPaperId = ref(null)
const studentName = ref(localStorage.getItem('student_name') || '同学')
const quizCounts = ref({ single: 3, multiple: 0, judge: 2, blank: 1, short: 1 })
const quizPassages = ref(0)
// 组卷配置在 subjects.js 各科目的 quiz / quizTypes（单一事实源）
const quizConfig = ref([])
const wrongBook = ref([])
// 老师布置的指定卷
const quizIsAssign = ref(false)
const assignPapers = ref([])
const assignLoading = ref(false)

function multiKey(qid) { return 'mul_' + qid }

function updateMulti(qid, checked, opt) {
  const key = multiKey(qid)
  if (!quizAnswers.value[key]) quizAnswers.value[key] = []
  const arr = quizAnswers.value[key]
  const idx = arr.indexOf(opt[0])
  if (checked && idx < 0) arr.push(opt[0])
  if (!checked && idx >= 0) arr.splice(idx, 1)
  quizAnswers.value[qid] = arr.join('')
}

function goHome() {
  view.value = 'home'
  activeSubject.value = null
  quizSubject.value = null
  quizResult.value = null
  quizMode.value = ''
  quizQuestions.value = []
}

// ============ 对话 ============
const chatBodyRef = ref(null)

function nowTime() {
  const d = new Date()
  return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
}

function scrollToBottom() {
  nextTick(() => {
    const el = chatBodyRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function openChat(subject) {
  activeSubject.value = subject
  view.value = 'chat'
  showHistory.value = false
  // 恢复本地历史：默认打开最近一次会话（继续上次聊），没有则开新会话
  chatSessions.value = await loadChatSessions(subject.id)
  const last = chatSessions.value[0]
  if (last) {
    currentSession.value = last
    messages.value = last.messages.map(m => ({ ...m }))
  } else {
    currentSession.value = { id: Date.now(), title: '', time: nowTime(), messages: [] }
    messages.value = []
  }
  await startSession(subject)
  nextTick(() => document.querySelector('.chat-input')?.focus())
}

function persistSession() {
  if (!currentSession.value || !activeSubject.value) return
  const firstUser = currentSession.value.messages.find(m => m.role === 'user')
  currentSession.value.time = nowTime()
  if (firstUser) currentSession.value.title = firstUser.content.slice(0, 24)
  saveChatSession(activeSubject.value.id, { ...currentSession.value }).then(() => {
    loadChatSessions(activeSubject.value.id).then(list => { chatSessions.value = list })
  })
}

async function startSession(subject) {
  if (isDemo) return // demo 模式无 MaxKB，LLM 经 Worker 代理直连
  chatId.value = ''
  chatToken.value = ''
  try {
    const res = await fetch('/chat/api/auth/anonymous', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: subject.accessToken }),
    })
    const data = await res.json()
    chatToken.value = data.data
    const openRes = await fetch('/chat/api/open', {
      method: 'GET',
      headers: { Authorization: 'Bearer ' + chatToken.value },
    })
    const openData = await openRes.json()
    chatId.value = openData.data
  } catch (e) {
    messages.value.push({ role: 'ai', content: '连接失败：' + e.message, time: nowTime() })
  }
}

async function newChat() {
  if (!activeSubject.value) return
  currentSession.value = { id: Date.now(), title: '', time: nowTime(), messages: [] }
  messages.value = []
  showHistory.value = false
  await startSession(activeSubject.value)
}

// ---- 历史会话操作 ----
async function openHistorySession(s) {
  currentSession.value = s
  messages.value = s.messages.map(m => ({ ...m }))
  showHistory.value = false
  await startSession(activeSubject.value)
}

async function removeSession(id) {
  if (!confirm('删除这条聊天记录？')) return
  await deleteChatSession(activeSubject.value.id, id)
  chatSessions.value = await loadChatSessions(activeSubject.value.id)
  if (currentSession.value?.id === id) newChat()
}

async function clearAllSessions() {
  if (!confirm('清空当前科目的全部聊天记录？')) return
  await clearChatSessions(activeSubject.value.id)
  chatSessions.value = []
  newChat()
}

function sendQuick(q) {
  input.value = q
  sendMessage()
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || chatLoading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text, time: nowTime() })
  currentSession.value.messages.push({ role: 'user', content: text, time: nowTime() })
  persistSession()
  chatLoading.value = true
  scrollToBottom()
  try {
    if (isDemo) {
      if (!api.hasLlmProxy()) {
        messages.value.push({ role: 'ai', content: '演示版未接入 AI 服务，请在本地完整版体验 AI 答疑。', time: nowTime() })
        return
      }
      const history = currentSession.value.messages.slice(-8)
      const r = await api.chatSend(activeSubject.value.id, text, history)
      messages.value.push({ role: 'ai', content: r.content, time: nowTime() })
      currentSession.value.messages.push({ role: 'ai', content: r.content, time: nowTime() })
      persistSession()
      return
    }
    const res = await fetch(`/chat/api/chat_message/${chatId.value}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + chatToken.value,
      },
      body: JSON.stringify({ message: text, stream: false, re_chat: false }),
    })
    const data = await res.json()
    const answer = data.data?.content || '（无回复）'
    messages.value.push({ role: 'ai', content: answer, time: nowTime() })
    currentSession.value.messages.push({ role: 'ai', content: answer, time: nowTime() })
    persistSession()
  } catch (e) {
    messages.value.push({ role: 'ai', content: '请求失败：' + e.message, time: nowTime() })
  } finally {
    chatLoading.value = false
    scrollToBottom()
  }
}

// ============ 自测 ============
const quizGradeMode = ref(false) // AI 判分体验模式：突出判分能力（客观秒判/简答 AI 评分）

function openQuiz(subject, gradeMode = false) {
  view.value = 'quiz'
  quizSubject.value = subject
  quizQuestions.value = []
  quizAnswers.value = {}
  quizResult.value = null
  quizPaperId.value = null
  quizIsAssign.value = false
  quizGradeMode.value = gradeMode
  // 科目配置了 quizTypes → 先进题型选择面板（判分模式默认只勾 gradePreselect）
  if (subject.quizTypes && subject.quizTypes.length) {
    quizMode.value = 'setup'
    quizConfig.value = subject.quizTypes.filter(t => !t.hidden).map(t => {
      if (!gradeMode) return { ...t }
      const on = t.kp === subject.gradePreselect
      return { ...t, enabled: on, count: on ? Math.min(3, t.max) : t.count }
    })
    return
  }
  // 否则按默认配置直接组卷
  quizMode.value = 'doing'
  const cfg = subject.quiz || { counts: { single: 5 }, passages: 0 }
  quizCounts.value = { ...cfg.counts }
  quizPassages.value = cfg.passages || 0
  startQuiz(subject)
}

// 主页特性卡入口：AI 判分 → 判分模式自测
function openGrade(subject) {
  openQuiz(subject, true)
}

// ============ 主页特性卡 → 选科目弹窗 ============
const featurePicker = ref(null) // null | 'chat' | 'quiz' | 'grade'
const featureMeta = {
  chat: { title: 'AI 答疑', desc: '选择科目，进入 AI 答疑（支持多会话与历史记录）' },
  quiz: { title: '智能组卷', desc: '选择科目，按知识点与题型一键成卷' },
  grade: { title: 'AI 判分', desc: '客观题提交秒判；简答题（如四级翻译）由 AI 智能评分' },
}
function openFeature(kind) {
  featurePicker.value = kind
}
function pickFeatureSubject(s) {
  const kind = featurePicker.value
  featurePicker.value = null
  if (kind === 'chat') openChat(s)
  else if (kind === 'quiz') openQuiz(s)
  else if (kind === 'grade') openGrade(s)
}

function beginQuiz() {
  const sel = quizConfig.value.filter(t => t.enabled && t.count > 0)
  if (!sel.length) {
    message.error('请至少选择一种题型')
    return
  }
  quizMode.value = 'doing'
  quizQuestions.value = []
  quizAnswers.value = {}
  quizResult.value = null
  quizPaperId.value = null
  startQuiz(quizSubject.value)
}

// 再来一套: 指定卷回到卷列表; 英语复用当前题型配置重开; 数学走 openQuiz
function redoQuiz() {
  if (quizIsAssign.value) { openAssignList(); return }
  if (quizSubject.value.id === 'english' && quizConfig.value.length) {
    quizMode.value = 'doing'
    quizQuestions.value = []
    quizAnswers.value = {}
    quizResult.value = null
    quizPaperId.value = null
    startQuiz(quizSubject.value)
  } else {
    openQuiz(quizSubject.value)
  }
}

// ============ 老师布置的指定卷 ============
async function openAssignList() {
  quizMode.value = 'assign'
  quizIsAssign.value = false
  assignLoading.value = true
  assignPapers.value = []
  try {
    const d = await api.assignPapers(quizSubject.value.id)
    assignPapers.value = d.items || []
  } catch (e) { assignPapers.value = [] }
  assignLoading.value = false
}

// 切回随机自测: 有题型面板的科目进 setup, 否则直接组卷
function toRandomQuiz() {
  quizIsAssign.value = false
  quizGradeMode.value = false
  const sub = getSubject(quizSubject.value.id)
  if (sub.quizTypes && sub.quizTypes.length) {
    quizMode.value = 'setup'
    quizConfig.value = sub.quizTypes.filter(t => !t.hidden).map(t => ({ ...t }))
  } else {
    quizMode.value = 'doing'
    quizQuestions.value = []
    quizAnswers.value = {}
    quizResult.value = null
    quizPaperId.value = null
    startQuiz(quizSubject.value)
  }
}

async function takeAssignPaper(p) {
  quizIsAssign.value = true
  quizMode.value = 'doing'
  quizQuestions.value = []
  quizAnswers.value = {}
  quizResult.value = null
  quizLoading.value = true
  try {
    const d = await api.getPaper(p.id)
    quizPaperId.value = p.id
    quizQuestions.value = d.questions || []
  } catch (e) { message.error('加载试卷失败：' + e.message) }
  quizLoading.value = false
}

async function startQuiz(subject) {
  quizLoading.value = true
  try {
    const isEn = subject.id === 'english'
    const kpConfig = {}
    if (isEn) {
      for (const t of quizConfig.value) {
        if (t.enabled && t.count > 0) kpConfig[t.kp] = t.count
      }
    }
    const data = await api.createPaper({
      subject: subject.id,
      title: `${subject.name}智能组卷`,
      counts: isEn ? { single: 0, multiple: 0, judge: 0, blank: 0, short: 1 } : quizCounts.value,
      passages: isEn ? 0 : quizPassages.value,
      knowledge_points: kpConfig,
    })
    if (data.code !== 200) {
      message.error('组卷失败：' + (data.detail || '题库暂无题目'))
      quizMode.value = ''
      return
    }
    quizPaperId.value = data.paper_id
    const paperData = await api.getPaper(data.paper_id)
    quizQuestions.value = paperData.questions
  } catch (e) {
    message.error('组卷失败：' + e.message)
    quizMode.value = ''
  } finally {
    quizLoading.value = false
  }
}

async function submitQuiz() {
  const unanswered = quizQuestions.value.filter(q => !quizAnswers.value[q.id] && q.qtype !== 'multiple').length
  const multiUnanswered = quizQuestions.value.filter(q => q.qtype === 'multiple' && !quizAnswers.value[multiKey(q.id)]?.length).length
  if ((unanswered + multiUnanswered) > 0 && !confirm(`还有 ${unanswered + multiUnanswered} 题未作答，确定提交吗？`)) return
  quizLoading.value = true
  try {
    const answers = {}
    for (const q of quizQuestions.value) {
      if (q.qtype === 'multiple') {
        answers[q.id] = (quizAnswers.value[multiKey(q.id)] || []).join('')
      } else {
        answers[q.id] = quizAnswers.value[q.id] || ''
      }
    }
    const data = await api.submitPaper(quizPaperId.value, { answers })
    localStorage.setItem('student_name', studentName.value)
    quizResult.value = data
    quizMode.value = 'done'
    if (data.results) await addPersonalWrong(data.results, quizQuestions.value)
    loadWrongBook()
  } catch (e) {
    message.error('提交失败：' + e.message)
  } finally {
    quizLoading.value = false
  }
}

async function loadWrongBook() {
  // 合并：服务端示例错题（tag 示例）+ 本机个人错题（storage.js，将来按账号存）
  let demo = []
  if (!isDemo) {
    try {
      const data = await api.wrongBook(studentName.value)
      demo = (data.items || []).map(w => ({ ...w, demo: true }))
    } catch (e) {}
  }
  const local = await loadWrongData()
  const merged = [
    ...local.entries,
    ...demo.filter(w => !local.hiddenDemoIds.includes(w.id)).map(w => ({
      ...w,
      mastered: local.demoMastered[w.id] !== undefined ? local.demoMastered[w.id] : w.mastered,
      note: local.demoNotes[w.id] || w.note || '',
    })),
  ]
  wrongBook.value = merged
}

// ---- 错题本个人操作（增删改） ----
async function addPersonalWrong(results, questions) {
  const local = await loadWrongData()
  for (const q of questions) {
    const r = results[q.id]
    if (!r || r.correct) continue
    local.entries.unshift({
      id: 'p' + Date.now() + '_' + q.id,
      time: new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }),
      subject: quizSubject.value.id,
      qtype: q.qtype,
      stem: q.stem,
      answer: r.std_answer || q.answer || '',
      analysis: r.analysis || q.analysis || '',
      knowledge_point: q.knowledge_point || '',
      student_answer: r.student_answer || '',
      note: '',
      mastered: false,
    })
  }
  await saveWrongData(local)
}

async function removeWrong(w) {
  if (!confirm('删除这条错题记录？')) return
  const local = await loadWrongData()
  if (w.demo) {
    local.hiddenDemoIds.push(w.id)
  } else {
    local.entries = local.entries.filter(e => e.id !== w.id)
  }
  await saveWrongData(local)
  loadWrongBook()
}

async function toggleWrongMastered(w) {
  const local = await loadWrongData()
  if (w.demo) {
    local.demoMastered[w.id] = !w.mastered
  } else {
    const e = local.entries.find(x => x.id === w.id)
    if (e) e.mastered = !w.mastered
  }
  await saveWrongData(local)
  loadWrongBook()
}

const noteEditingId = ref('')
const noteDraft = ref('')
function editWrongNote(w) {
  noteEditingId.value = w.id
  noteDraft.value = w.note || ''
}
async function saveWrongNote(w) {
  const local = await loadWrongData()
  if (w.demo) {
    local.demoNotes[w.id] = noteDraft.value
  } else {
    const e = local.entries.find(x => x.id === w.id)
    if (e) e.note = noteDraft.value
  }
  await saveWrongData(local)
  noteEditingId.value = ''
  loadWrongBook()
}

// 错题强化闭环：基于未掌握错题的知识点重新组卷 → 作答 → 判卷后做对自动移出错题本
const reviewLoading = ref(false)
const wrongFilter = ref('all') // all | math | english
const wrongFiltered = computed(() =>
  wrongBook.value.filter(w => wrongFilter.value === 'all' || w.subject === wrongFilter.value))
const unmasteredBySub = computed(() => {
  const m = {}
  for (const w of wrongBook.value) if (!w.mastered) m[w.subject] = (m[w.subject] || 0) + 1
  return m
})
async function startReview(subject) {
  if (reviewLoading.value) return
  const unmastered = wrongBook.value.filter(w => !w.mastered && w.subject === subject)
  if (!unmastered.length) {
    message.error('该科目当前没有待巩固的错题')
    return
  }
  const subjObj = getSubject(subject)
  reviewLoading.value = true
  try {
    const data = await api.reviewPaper({ student_name: studentName.value, subject: subjObj.id })
    if (data.code !== 200) {
      const d = data.detail
      message.error('重练组卷失败：' + (typeof d === 'string' ? d : '暂无薄弱点'))
      return
    }
    quizSubject.value = subjObj
    quizPaperId.value = data.paper_id
    quizMode.value = 'doing'
    quizQuestions.value = []
    quizAnswers.value = {}
    quizResult.value = null
    view.value = 'quiz'
    quizLoading.value = true
    try {
      const paperData = await api.getPaper(data.paper_id)
      quizQuestions.value = paperData.questions
    } finally {
      quizLoading.value = false
    }
  } catch (e) {
    message.error('错题重练失败：' + (e.message || '请稍后重试'))
  } finally {
    reviewLoading.value = false
  }
}

onMounted(async () => {
  loadWrongBook()
  try {
    const data = await api.stats()
    const st = {}
    for (const s of SUBJECTS) st[s.id] = data.items?.[s.id]?.total || 0
    bankStats.value = st
  } catch (e) {}
  for (const s of SUBJECTS) {
    try {
      kbParas.value[s.id] = await api.kbParagraphCount(s.id)
    } catch (e) {}
  }
})
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
  <div class="app">
    <header class="header">
      <div class="header-inner">
        <div class="brand">
          <span class="brand-mark"><AppIcon name="cap" :size="20" /></span>
          <div class="brand-text">
            <h1 class="logo">AI 教辅智学平台</h1>
            <p class="subtitle">青岛理工大学 AI 应用创新开发大赛 · 教学赋能类</p>
          </div>
        </div>
        <div class="nav">
          <button :class="{ active: view === 'home' }" @click="goHome">科目</button>
        </div>
      </div>
    </header>

    <main class="main">
      <!-- ======== 科目选择页（首页 · 双栏工作台） ======== -->
      <div v-if="view === 'home'" class="subject-page">
        <!-- Hero（紧凑居中） -->
        <section class="hero v3-hero">
          <div class="hero-badge"><AppIcon name="sparkles" :size="13" /> AI 驱动 · RAG 知识库答疑</div>
          <h2 class="hero-title">会学习的 <span class="grad">AI 助教</span>，陪你把课程吃透</h2>
          <p class="hero-sub">智能答疑 · 在线自测 · 错题追踪 —— 基于课程知识库，答有所据</p>
        </section>

        <div class="workbench">
          <!-- 左栏：科目 + 功能 -->
          <div class="wb-main">
            <h3 class="section-label">我的科目</h3>
            <div class="subject-list">
              <div v-for="s in subjects" :key="s.id" class="subject-card v3" :style="{ '--accent': s.color, '--accent2': s.color2 || s.color }">
                <div class="v3-head">
                  <div class="subject-icon">{{ s.icon }}</div>
                  <div class="subject-titles">
                    <div class="subject-name">{{ s.name }} <span class="v3-en">{{ s.enName }}</span></div>
                    <div class="v3-desc">{{ s.desc }}</div>
                  </div>
                  <div class="v3-chips">
                    <span class="chip-stat"><b>{{ bankStats[s.id] || 0 }}</b>题库</span>
                    <span class="chip-stat"><b>{{ kbParas[s.id] || 0 }}</b>知识段</span>
                  </div>
                </div>
                <div class="v3-actions">
                  <button class="v3-act primary" @click="openChat(s)"><AppIcon name="chat" :size="16" /> AI 答疑</button>
                  <button class="v3-act" @click="openQuiz(s)"><AppIcon name="pencil" :size="16" /> 在线自测</button>
                  <button class="v3-act" @click="openGrade(s)"><AppIcon name="check" :size="16" /> AI 判分</button>
                  <button class="v3-act ghost" @click="openKnowledge(s)"><AppIcon name="book" :size="16" /> 知识库</button>
                </div>
              </div>
            </div>

            <h3 class="section-label">学习功能</h3>
            <div class="features-grid v3">
              <div class="feature-card clickable" @click="openFeature('chat')"><AppIcon name="zap" class="feature-ic" /><div class="feature-txt"><b>AI 答疑</b><span>知识库检索增强，答有所据不瞎编</span></div><AppIcon name="arrow_right" class="feature-go" :size="15" /></div>
              <div class="feature-card clickable" @click="openFeature('quiz')"><AppIcon name="target" class="feature-ic" /><div class="feature-txt"><b>智能组卷</b><span>按知识点与题型抽题，一键成卷</span></div><AppIcon name="arrow_right" class="feature-go" :size="15" /></div>
              <div class="feature-card clickable" @click="openFeature('grade')"><AppIcon name="check" class="feature-ic" /><div class="feature-txt"><b>AI 判分</b><span>客观题秒判，简答题 AI 智能评分</span></div><AppIcon name="arrow_right" class="feature-go" :size="15" /></div>
              <div class="feature-card clickable" @click="loadWrongBook(); view = 'wrong'"><AppIcon name="trophy" class="feature-ic" /><div class="feature-txt"><b>错题追踪<em v-if="wrongBook.length" class="feature-badge">{{ wrongBook.length }}</em></b><span>错题自动收录，循环巩固到掌握</span></div><AppIcon name="arrow_right" class="feature-go" :size="15" /></div>
            </div>
          </div>

          <!-- 右栏：侧栏 -->
          <aside class="wb-side">
            <div class="side-card">
              <h3 class="side-title">平台数据</h3>
              <div class="side-stats">
                <div class="stat"><span class="stat-num">{{ sumOf(bankStats) }}</span><span class="stat-label">精品题库</span></div>
                <div class="stat"><span class="stat-num">{{ sumOf(kbParas) }}+</span><span class="stat-label">知识库段落</span></div>
                <div class="stat"><span class="stat-num">700+</span><span class="stat-label">核心知识点</span></div>
                <div class="stat"><span class="stat-num">AI</span><span class="stat-label">实时判分</span></div>
              </div>
            </div>

            <div class="side-card accent-card" @click="loadWrongBook(); view = 'wrong'">
              <h3 class="side-title"><AppIcon name="trophy" :size="16" /> 错题追踪</h3>
              <template v-if="wrongBook.length">
                <div class="side-big">{{ wrongBook.filter(w => !w.mastered).length }}</div>
                <p class="side-sub">道待巩固错题 · 点击进入错题本</p>
              </template>
              <template v-else>
                <p class="side-sub alone">暂无错题，先去自测练一套吧<br />做错的题会自动收进错题本 →</p>
              </template>
            </div>

            <button v-if="!isDemo" class="side-card teacher-card" @click="view = 'teacher'">
              <h3 class="side-title"><AppIcon name="chart" :size="16" /> 教师端</h3>
              <p class="side-sub alone">题库管理 · 组卷布置<br />学情看板 · AI 诊断报告</p>
              <span class="side-go">进入管理 <AppIcon name="arrow_right" :size="13" /></span>
            </button>
          </aside>
        </div>
      </div>

      <!-- ======== 教师端（独立组件） ======== -->
      <Teacher v-else-if="view === 'teacher'" @back="goHome" />

      <!-- ======== 错题本 ======== -->
      <div v-else-if="view === 'wrong'" class="wrong-page">
        <div class="page-head">
          <n-button quaternary class="back-btn" @click="goHome"><AppIcon name="back" :size="16" /> 返回</n-button>
          <h2 class="page-title">我的错题本</h2>
          <div class="wrong-filter">
            <button :class="{ active: wrongFilter === 'all' }" @click="wrongFilter = 'all'">全部 {{ wrongBook.length }}</button>
            <button v-for="s in subjects" :key="s.id" :class="{ active: wrongFilter === s.id }" @click="wrongFilter = s.id">
              {{ s.name }} {{ wrongBook.filter(w => w.subject === s.id).length }}
            </button>
          </div>
          <div v-if="Object.keys(unmasteredBySub).length" class="review-bar">
            <n-button v-for="(cnt, sid) in unmasteredBySub" :key="sid" type="primary" size="small"
              :loading="reviewLoading" @click="startReview(sid)">
              <span style="display:inline-flex;align-items:center;gap:6px"><AppIcon name="book_marked" :size="15" />
                {{ (subjects.find(x => x.id === sid)?.name || sid) + '重练（' + cnt + '）' }}</span>
            </n-button>
          </div>
        </div>
        <div v-if="!wrongFiltered.length" class="empty-tip">{{ wrongFilter === 'all' ? '暂无错题，去自测一下吧！' : '该科目暂无错题' }}</div>
        <div v-else class="wrong-list">
          <div v-for="w in wrongFiltered" :key="w.id" class="wrong-card">
            <div class="wrong-head">
              <div class="wrong-tags">
                <span class="wrong-tag">{{ w.subject === 'math' ? '高数' : '英语' }} · {{ typeLabels[w.qtype] }}</span>
                <span v-if="w.demo" class="demo-tag">示例</span>
                <span v-if="w.mastered" class="mastered-tag"><AppIcon name="check" :size="11" /> 已掌握</span>
              </div>
              <div class="wrong-ops">
                <button class="op-btn" :title="w.mastered ? '标记为未掌握' : '标记为已掌握'" @click="toggleWrongMastered(w)">
                  <AppIcon name="check" :size="14" />
                </button>
                <button class="op-btn" title="写笔记" @click="editWrongNote(w)"><AppIcon name="pencil" :size="14" /></button>
                <button class="op-btn danger" title="删除" @click="removeWrong(w)"><AppIcon name="x" :size="14" /></button>
              </div>
            </div>
            <div class="wrong-stem"><MarkdownRender :content="w.stem" /></div>
            <div class="wrong-detail">
              <div v-if="w.qtype === 'short'" class="wrong-answer answer-md">参考解答：<MarkdownRender :content="w.answer" /></div>
              <div v-else-if="w.qtype === 'blank'" class="wrong-answer answer-md">正确答案：<MarkdownRender :content="w.answer" /></div>
              <div v-else class="wrong-answer">正确答案：<span class="correct">{{ w.answer }}</span></div>
              <div v-if="w.analysis" class="wrong-analysis"><strong>解析：</strong><MarkdownRender :content="w.analysis" /></div>
              <div v-if="w.note && noteEditingId !== w.id" class="wrong-note"><AppIcon name="pencil" :size="12" /> 我的笔记：{{ w.note }}</div>
              <div v-if="noteEditingId === w.id" class="wrong-note-edit">
                <input v-model="noteDraft" class="note-input" placeholder="记点什么，比如错因、思路…" @keyup.enter="saveWrongNote(w)" />
                <button class="op-btn ok" @click="saveWrongNote(w)"><AppIcon name="check" :size="13" /> 保存</button>
              </div>
            </div>
            <div class="wrong-foot">
              <span class="kp">知识点：{{ w.knowledge_point }}</span>
              <span v-if="w.student_answer" class="kp">你的答案：{{ w.student_answer }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ======== 知识库页 ======== -->
      <div v-else-if="view === 'kb'" class="kb-page">
        <div class="page-head">
          <n-button quaternary class="back-btn" @click="goHome"><AppIcon name="back" :size="16" /> 返回</n-button>
          <h2 class="page-title">{{ kbSubject.name }} · 知识库</h2>
          <div class="kb-search-bar inline">
            <n-input v-model:value="kbSearchQuery" placeholder="检索知识点…" @keyup.enter="kbSearch" clearable />
            <n-button type="primary" :loading="kbSearching" :disabled="!kbSearchQuery.trim()" @click="kbSearch">检索</n-button>
          </div>
        </div>

        <!-- 检索模式 -->
        <div v-if="kbError" class="wrong-list">
          <n-alert type="error" :bordered="false">{{ kbError }}</n-alert>
        </div>

        <div v-else-if="kbLoading" class="kb-book" style="justify-content:center; padding:60px 0">
          <n-spin size="large"><template #description>知识库加载中…</template></n-spin>
        </div>

        <!-- 检索模式 -->
        <div v-else-if="kbResults.length" class="wrong-list">
          <h3 class="kb-section-title">检索结果（{{ kbResults.length }}）</h3>
          <div v-for="(r, i) in kbResults" :key="i" class="wrong-card">
            <div class="wrong-tag">相似度 {{ (r.similarity * 100).toFixed(0) }}% · {{ r.document_name }}</div>
            <div class="kb-result-title">{{ r.title }}</div>
            <div class="wrong-stem"><MarkdownRender :content="r.content" /></div>
          </div>
          <n-button quaternary @click="kbResults = []; kbSearchQuery = ''">← 返回目录</n-button>
        </div>

        <!-- 书式浏览 -->
        <div v-else class="kb-book">
          <aside class="kb-sidebar">
            <div class="kb-side-title">章</div>
            <button v-for="d in kbDocs" :key="d.id" class="kb-toc-item" :class="{ active: kbCurrentDoc && kbCurrentDoc.id === d.id }" @click="openDoc(d)">
              {{ docDisplayName(d.name) }}
            </button>
          </aside>
          <div class="kb-mid">
            <div class="kb-side-title">{{ kbCurrentDoc ? '节 · ' + docDisplayName(kbCurrentDoc.name) + '（' + kbSections.length + '）' : '节（0）' }}</div>
            <button v-for="(sec, i) in kbSections" :key="sec.id" class="kb-sec-item" :class="{ active: kbCurrentSection && kbCurrentSection.id === sec.id }" @click="selectSection(sec)">
              <span class="kb-sec-num">{{ i + 1 }}</span>
              <span class="kb-sec-name">{{ sec.title }}</span>
            </button>
          </div>
          <div class="kb-content">
            <div v-if="!kbCurrentSection" class="empty-tip">请选择知识点</div>
            <div v-else class="kb-section-body">
              <h2 class="kb-section-title2">{{ kbCurrentSection.title }}</h2>
              <MarkdownRender :content="kbCurrentSection.content" />
            </div>
          </div>
        </div>
      </div>

      <!-- ======== 对话页 ======== -->
      <div v-else-if="view === 'chat'" class="chat-page" :style="{ '--accent': activeSubject.color }">
        <div class="chat-header">
          <n-button quaternary class="back-btn" @click="goHome"><AppIcon name="back" :size="16" /> 返回</n-button>
          <div class="chat-title">
            <span class="chat-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</span>
            <div class="chat-title-text">
              <span class="chat-name">{{ activeSubject.name }} · AI 答疑</span>
              <span class="chat-status"><i class="dot"></i>在线</span>
            </div>
          </div>
          <n-button size="small" style="margin-left:auto" @click="newChat"><AppIcon name="rotate" :size="15" /> 新对话</n-button>
          <n-button size="small" @click="showHistory = !showHistory"><AppIcon name="clipboard" :size="15" /> 记录</n-button>
          <div class="chat-model">DeepSeek</div>
        </div>

        <div ref="chatBodyRef" class="chat-body">
          <!-- 欢迎屏 -->
          <div v-if="!messages.length && !chatLoading" class="welcome">
            <div class="welcome-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</div>
            <h3 class="welcome-title">你好，我是{{ activeSubject.name }}AI助教</h3>
            <p class="welcome-desc">基于课程知识库的智能答疑助手，可以问我任何问题</p>
            <div class="quick-chips">
              <button v-for="q in (activeSubject.chatQuickQuestions || [])" :key="q" class="chip" @click="sendQuick(q)">{{ q }}</button>
            </div>
          </div>

          <!-- 消息区 -->
          <template v-else>
            <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
              <div v-if="m.role === 'ai'" class="msg-avatar" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</div>
              <div class="msg-content">
                <div class="msg-bubble"><MarkdownRender :content="m.content" /></div>
                <div v-if="m.time" class="msg-time">{{ m.time }}</div>
              </div>
              <div v-if="m.role === 'user'" class="msg-avatar user-avatar">我</div>
            </div>

            <!-- 打字动画 -->
            <div v-if="chatLoading" class="msg-row ai">
              <div class="msg-avatar" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</div>
              <div class="msg-content">
                <div class="msg-bubble typing-dots"><i></i><i></i><i></i></div>
              </div>
            </div>
          </template>
        </div>

        <!-- 聊天记录抽屉（本地专属存储） -->
        <div v-if="showHistory" class="history-mask" @click="showHistory = false">
          <aside class="history-panel" @click.stop>
            <div class="history-head">
              <b><AppIcon name="clipboard" :size="15" /> 聊天记录 · {{ activeSubject.name }}</b>
              <span class="history-tip">保存在本机</span>
              <button class="h-op" @click="clearAllSessions">清空</button>
            </div>
            <div v-if="!chatSessions.length" class="empty-tip">暂无历史会话</div>
            <div v-for="s in chatSessions" :key="s.id" class="history-item"
              :class="{ cur: currentSession && currentSession.id === s.id }" @click="openHistorySession(s)">
              <div class="h-title">{{ s.title || '新对话' }}</div>
              <div class="h-meta">{{ s.time }} · {{ s.messages.length }} 条消息</div>
              <button class="h-del" title="删除" @click.stop="removeSession(s.id)"><AppIcon name="x" :size="13" /></button>
            </div>
          </aside>
        </div>

        <div class="chat-input-area">
          <n-input v-model:value="input" size="large" placeholder="输入你的问题，回车发送…" @keyup.enter="sendMessage" :disabled="chatLoading" />
          <n-button type="primary" circle size="large" :loading="chatLoading" :disabled="!input.trim()" @click="sendMessage"><AppIcon name="send" :size="17" /></n-button>
        </div>
      </div>

      <!-- ======== 自测页 ======== -->
      <div v-else-if="view === 'quiz'" class="quiz-page">
        <div class="chat-header">
          <n-button quaternary class="back-btn" @click="goHome"><AppIcon name="back" :size="16" /> 返回</n-button>
          <div class="chat-title">
            <span class="chat-icon" :style="{ background: quizSubject.color }">{{ quizSubject.icon }}</span>
            <span>{{ quizSubject.name }} · 智能自测</span>
          </div>
          <div class="chat-model">{{ quizMode === 'setup' ? '题型选择' : quizMode === 'done' ? '已判卷' : quizMode === 'assign' ? '老师布置的试卷' : '在线作答' }}</div>
        </div>

        <!-- 随机自测 / 老师布置的卷 切换 -->
        <div class="quiz-mode-tabs">
          <button :class="{ active: quizMode !== 'assign' && !quizIsAssign }" @click="toRandomQuiz"><AppIcon name="shuffle" :size="15" /> 随机自测</button>
          <button :class="{ active: quizMode === 'assign' }" @click="openAssignList"><AppIcon name="clipboard" :size="15" /> 老师布置的试卷</button>
        </div>

        <template v-if="quizMode === 'assign'">
          <div class="assign-area">
            <h3 class="page-desc">老师布置的试卷 · {{ quizSubject.name }}（选一份开始作答）</h3>
            <div v-if="assignLoading" class="empty-tip">加载中…</div>
            <div v-else-if="!assignPapers.length" class="empty-tip">老师还没有布置试卷，切回"随机自测"练一练吧</div>
            <div v-else class="paper-list assign-list">
              <div v-for="p in assignPapers" :key="p.id" class="paper-row">
                <div class="paper-info">
                  <div class="paper-title">{{ p.title }}</div>
                  <div class="paper-sub">{{ p.create_time }} · {{ p.q_count }} 题</div>
                </div>
                <n-button type="primary" @click="takeAssignPaper(p)">开始作答</n-button>
              </div>
            </div>
          </div>
        </template>

        <template v-if="quizMode === 'setup'">
          <div class="quiz-setup">
            <div class="setup-tip">选择本次自测要练习的题型（阅读按"篇"抽题，每篇含 5 道真题）</div>
            <div class="setup-list">
              <div v-for="t in quizConfig" :key="t.kp" class="setup-row" :class="{ on: t.enabled }">
                <n-checkbox v-model:checked="t.enabled" class="setup-toggle">
                  <span class="setup-name">{{ t.label }}</span>
                  <span class="setup-count">{{ t.kp === '阅读' ? '真题 ' + (t.max * 5) + ' 题' : '共 ' + t.max + ' 题' }}</span>
                </n-checkbox>
                <div v-if="t.enabled" class="setup-stepper">
                  <button class="step-btn" @click="t.count > 1 && t.count--">−</button>
                  <span class="step-val">{{ t.count }} {{ t.unit }}</span>
                  <button class="step-btn" @click="t.count < t.max && t.count++">+</button>
                </div>
              </div>
            </div>
            <div class="quiz-submit-bar">
              <n-button type="primary" @click="beginQuiz">开始自测</n-button>
            </div>
          </div>
        </template>

        <template v-if="quizMode === 'doing'">
          <div v-if="quizGradeMode" class="grade-banner">
            <AppIcon name="check" :size="15" />
            <span>{{ quizSubject?.gradeHint || 'AI 判分体验：提交后客观题秒判，简答题由 AI 智能评分' }}</span>
          </div>
          <div v-if="quizLoading" class="empty-tip">正在智能组卷…</div>
          <div v-else class="quiz-body">
            <div class="quiz-list">
              <template v-for="(q, qi) in quizQuestions" :key="q.id">
                <div v-if="q.passage && (qi === 0 || quizQuestions[qi-1].passage !== q.passage)" class="passage-card">
                  <div class="passage-title"><AppIcon name="file" :size="15" /> 阅读理解 · {{ q.passage_key }}</div>
                  <div class="passage-text"><MarkdownRender :content="q.passage" /></div>
                </div>
                <div class="quiz-card">
                <div class="quiz-head">
                  <span class="quiz-num">{{ qi + 1 }}</span>
                  <span class="quiz-type">{{ typeLabels[q.qtype] }}</span>
                  <span class="quiz-kp">{{ q.knowledge_point }}</span>
                </div>
                <div class="quiz-stem"><MarkdownRender :content="q.stem" /></div>

                <div v-if="q.qtype === 'single'" class="quiz-options">
                  <label v-for="opt in (q.options || [])" :key="opt" class="opt-item" :class="{ selected: quizAnswers[q.id] === opt[0] }">
                    <input type="radio" :name="'q' + q.id" :value="opt[0]" v-model="quizAnswers[q.id]" />
                    <span class="opt-text"><MarkdownRender :content="opt" /></span>
                  </label>
                </div>

                <div v-if="q.qtype === 'multiple'" class="quiz-options">
                  <label v-for="opt in (q.options || [])" :key="opt" class="opt-item" :class="{ selected: quizAnswers[multiKey(q.id)] && quizAnswers[multiKey(q.id)].includes(opt[0]) }">
                    <input type="checkbox" :value="opt[0]" :checked="quizAnswers[multiKey(q.id)] && quizAnswers[multiKey(q.id)].includes(opt[0])"
                      @change="updateMulti(q.id, $event.target.checked, opt)" />
                    <span class="opt-text"><MarkdownRender :content="opt" /></span>
                  </label>
                </div>

                <div v-if="q.qtype === 'judge'" class="quiz-options judge-options">
                  <label class="opt-item" :class="{ selected: quizAnswers[q.id] === '对' }">
                    <input type="radio" :name="'q' + q.id" value="对" v-model="quizAnswers[q.id]" /> 对
                  </label>
                  <label class="opt-item" :class="{ selected: quizAnswers[q.id] === '错' }">
                    <input type="radio" :name="'q' + q.id" value="错" v-model="quizAnswers[q.id]" /> 错
                  </label>
                </div>

                <div v-if="q.qtype === 'blank'" class="quiz-blank">
                  <input v-model="quizAnswers[q.id]" class="blank-input" placeholder="请输入答案" />
                </div>

                <div v-if="q.qtype === 'short'" class="quiz-short">
                  <textarea v-model="quizAnswers[q.id]" class="short-input" placeholder="请输入你的回答…" rows="6"></textarea>
                </div>
              </div>
              </template>
            </div>
            <div class="quiz-submit-bar">
              <div class="student-name">
                <span class="t-label">姓名：</span>
                <n-input v-model:value="studentName" placeholder="请输入姓名" style="width:160px" />
              </div>
              <n-button type="primary" :loading="quizLoading" @click="submitQuiz">提交并判卷</n-button>
            </div>
          </div>
        </template>

        <template v-if="quizMode === 'done' && quizResult">
          <div class="result-banner" :class="quizResult.score >= 60 ? 'pass' : 'fail'">
            <div class="result-score">{{ quizResult.score }}</div>
            <div class="result-label">得分 / {{ quizResult.total }}分</div>
            <div class="result-verdict">{{ quizResult.score >= 60 ? '已掌握，继续加油！' : '需复习，看看解析吧' }}</div>
          </div>
          <div class="quiz-body">
            <div class="quiz-list">
              <template v-for="(q, qi) in quizQuestions" :key="q.id">
                <div v-if="q.passage && (qi === 0 || quizQuestions[qi-1].passage !== q.passage)" class="passage-card">
                  <div class="passage-title"><AppIcon name="file" :size="15" /> 阅读理解 · {{ q.passage_key }}</div>
                  <div class="passage-text"><MarkdownRender :content="q.passage" /></div>
                </div>
                <div class="quiz-card" :class="quizResult.results[q.id]?.correct ? 'correct-card' : 'wrong-card2'">
                <div class="quiz-head">
                  <span class="quiz-num">{{ qi + 1 }}</span>
                  <span class="quiz-type">{{ typeLabels[q.qtype] }}</span>
                  <span class="quiz-mark" :class="quizResult.results[q.id]?.correct ? 'mark-right' : 'mark-wrong'">
                    <AppIcon :name="quizResult.results[q.id]?.correct ? 'check' : 'x'" :size="14" />
                    {{ quizResult.results[q.id]?.correct ? '正确' : '错误' }}
                  </span>
                </div>
                <div class="quiz-stem"><MarkdownRender :content="q.stem" /></div>
                <div class="result-detail">
                  <div class="result-line">你的答案：{{ quizResult.results[q.id]?.student_answer || '（未作答）' }}</div>
                  <div v-if="quizResult.results[q.id]?.needs_review" class="result-line needs-review-line"><AppIcon name="alert" :size="13" /> AI 判分失败，请老师复核</div>
                  <div v-if="!quizResult.results[q.id]?.correct && q.qtype === 'short'" class="result-line answer-md">参考解答：<MarkdownRender :content="quizResult.results[q.id]?.std_answer || ''" /></div>
                  <div v-else-if="!quizResult.results[q.id]?.correct && q.qtype === 'blank'" class="result-line answer-md">正确答案：<MarkdownRender :content="quizResult.results[q.id]?.std_answer || ''" /></div>
                  <div v-else-if="!quizResult.results[q.id]?.correct" class="result-line">正确答案：<span class="correct">{{ quizResult.results[q.id]?.std_answer }}</span></div>
                  <div v-if="quizResult.results[q.id]?.analysis" class="result-line">
                    <strong>解析：</strong><MarkdownRender :content="quizResult.results[q.id]?.analysis" />
                  </div>
                </div>
              </div>
              </template>
            </div>
            <div class="quiz-submit-bar">
              <n-button type="primary" @click="redoQuiz">再来一套</n-button>
              <n-button v-if="quizSubject.id === 'english'" quaternary @click="openQuiz(quizSubject)">调整题型</n-button>
              <n-button quaternary @click="loadWrongBook(); view = 'wrong'">查看错题本</n-button>
            </div>
          </div>
        </template>
      </div>
    </main>

    <footer class="footer">AI 教辅智学平台 · 智能教辅双端平台</footer>
  </div>

  <!-- ======== 特性入口 · 选科目弹窗 ======== -->
  <n-modal :show="!!featurePicker" preset="card" style="width: 520px" :bordered="false"
    :title="'🚀 ' + (featureMeta[featurePicker]?.title || '') + ' · 选择科目'"
    @close="featurePicker = null" :mask-closable="true">
    <p class="picker-desc">{{ featureMeta[featurePicker]?.desc }}</p>
    <div class="picker-grid">
      <div v-for="s in subjects" :key="s.id" class="subject-card picker-card" :style="{ '--accent': s.color }" @click="pickFeatureSubject(s)">
        <div class="subject-icon">{{ s.icon }}</div>
        <div class="subject-titles">
          <div class="subject-name">{{ s.name }}</div>
          <div class="subject-en">{{ s.enName }} · {{ bankStats[s.id] || 0 }} 题</div>
        </div>
        <AppIcon name="arrow_right" class="feature-go" :size="18" />
      </div>
    </div>
  </n-modal>
  <Mascot />
  </n-config-provider>
</template>
