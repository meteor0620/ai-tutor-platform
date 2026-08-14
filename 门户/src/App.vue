<script setup>
import { ref, onMounted, nextTick } from 'vue'
import MarkdownRender from './components/MarkdownRender.vue'
import Teacher from './components/Teacher.vue'

const subjects = [
  {
    id: 'math',
    name: '高等数学',
    enName: 'Calculus',
    desc: '函数极限 · 导数微分 · 积分 · 多元函数 · 微分方程',
    accessToken: 'a0db0c103acc013b',
    color: '#4f46e5',
    icon: '∫',
  },
  {
    id: 'english',
    name: '大学英语',
    enName: 'College English',
    desc: '核心词汇 · 语法 · 阅读理解 · 写作技巧',
    accessToken: '6a8aa556e0c7e490',
    color: '#0d9488',
    icon: 'A',
  },
]

const typeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', blank: '填空题', short: '简答题' }

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
  try {
    const res = await fetch(`/api/knowledge/${subject.id}/documents`)
    const data = await res.json()
    kbDocs.value = data.items || []
    if (kbDocs.value.length) openDoc(kbDocs.value[0])
  } catch (e) {}
}

async function openDoc(doc) {
  kbCurrentDoc.value = doc
  kbSections.value = []
  kbCurrentSection.value = null
  kbResults.value = []
  try {
    const res = await fetch(`/api/knowledge/${kbSubject.value.id}/documents/${doc.id}/sections`)
    const data = await res.json()
    kbSections.value = data.items || []
    if (kbSections.value.length) {
      kbCurrentSection.value = kbSections.value[0]
    }
  } catch (e) {}
}

function selectSection(sec) {
  kbCurrentSection.value = sec
}

async function kbSearch() {
  const q = kbSearchQuery.value.trim()
  if (!q) return
  kbSearching.value = true
  try {
    const res = await fetch(`/api/knowledge/${kbSubject.value.id}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: kbSubject.value.id, query: q, top_n: 5 }),
    })
    const data = await res.json()
    kbResults.value = data.items || []
  } catch (e) {
    kbResults.value = []
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
// 各科目自测配置: 数学走通用题库(固定), 英语走自主选题型
const SUBJECT_QUIZ = {
  math: { counts: { single: 3, multiple: 0, judge: 2, blank: 1, short: 1 }, passages: 0 },
  english: { counts: { single: 0, multiple: 0, judge: 0, blank: 0, short: 1 }, passages: 2 },
}
// 英语题型选择定义(阅读按"篇"抽题, 每篇5道真题; 翻译为真题简答; 其余为 demo 补充)
const ENGLISH_TYPES = [
  { kp: '阅读', label: '阅读理解', unit: '篇文章', max: 5, count: 1, enabled: true },
  { kp: '翻译', label: '段落翻译', unit: '道题', max: 9, count: 1, enabled: true },
  { kp: '词汇', label: '核心词汇', unit: '道题', max: 5, count: 3, enabled: false },
  { kp: '语法', label: '语法练习', unit: '道题', max: 5, count: 3, enabled: false },
  { kp: '写作', label: '写作技巧', unit: '道题', max: 3, count: 2, enabled: false },
  { kp: '听力', label: '听力理解', unit: '道题', max: 1, count: 1, enabled: false },
]
const quizConfig = ref([])
const wrongBook = ref([])

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
const quickQuestions = {
  math: ['泰勒展开是什么？', '导数的定义', '洛必达法则', '定积分怎么算'],
  english: ['解释一下虚拟语气', '定语从句怎么用', '作文常用句型', '高频核心词汇'],
}

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

function openChat(subject) {
  activeSubject.value = subject
  view.value = 'chat'
  startSession(subject)
  nextTick(() => document.querySelector('.chat-input')?.focus())
}

async function startSession(subject) {
  messages.value = []
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

function newChat() {
  if (activeSubject.value) startSession(activeSubject.value)
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
  chatLoading.value = true
  scrollToBottom()
  try {
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
  } catch (e) {
    messages.value.push({ role: 'ai', content: '请求失败：' + e.message, time: nowTime() })
  } finally {
    chatLoading.value = false
    scrollToBottom()
  }
}

// ============ 自测 ============
function openQuiz(subject) {
  view.value = 'quiz'
  quizSubject.value = subject
  quizQuestions.value = []
  quizAnswers.value = {}
  quizResult.value = null
  quizPaperId.value = null
  if (subject.id === 'english') {
    // 英语: 先出题型选择面板, 不立即组卷
    quizMode.value = 'setup'
    quizConfig.value = ENGLISH_TYPES.map(t => ({ ...t }))
    return
  }
  // 数学: 直接按默认配置组卷
  quizMode.value = 'doing'
  const cfg = SUBJECT_QUIZ[subject.id] || SUBJECT_QUIZ.math
  quizCounts.value = { ...cfg.counts }
  quizPassages.value = cfg.passages
  startQuiz(subject)
}

function beginQuiz() {
  const sel = quizConfig.value.filter(t => t.enabled && t.count > 0)
  if (!sel.length) {
    alert('请至少选择一种题型')
    return
  }
  quizMode.value = 'doing'
  quizQuestions.value = []
  quizAnswers.value = {}
  quizResult.value = null
  quizPaperId.value = null
  startQuiz(quizSubject.value)
}

// 再来一套: 英语复用当前题型配置直接重开, 数学走 openQuiz
function redoQuiz() {
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
    const res = await fetch('/api/papers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: subject.id,
        title: `${subject.name}智能组卷`,
        counts: isEn ? { single: 0, multiple: 0, judge: 0, blank: 0, short: 1 } : quizCounts.value,
        passages: isEn ? 0 : quizPassages.value,
        knowledge_points: kpConfig,
      }),
    })
    const data = await res.json()
    if (data.code !== 200) {
      alert('组卷失败：' + (data.detail || '题库暂无题目'))
      quizMode.value = ''
      return
    }
    quizPaperId.value = data.paper_id
    const paperRes = await fetch(`/api/papers/${data.paper_id}`)
    const paperData = await paperRes.json()
    quizQuestions.value = paperData.questions
  } catch (e) {
    alert('组卷失败：' + e.message)
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
    const res = await fetch(`/api/papers/${quizPaperId.value}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_id: quizPaperId.value,
        student_name: studentName.value,
        answers: answers,
      }),
    })
    const data = await res.json()
    localStorage.setItem('student_name', studentName.value)
    quizResult.value = data
    quizMode.value = 'done'
    loadWrongBook()
  } catch (e) {
    alert('提交失败：' + e.message)
  } finally {
    quizLoading.value = false
  }
}

async function loadWrongBook() {
  try {
    const res = await fetch(`/api/wrong-book?student_name=${encodeURIComponent(studentName.value)}`)
    const data = await res.json()
    wrongBook.value = data.items || []
  } catch (e) {}
}

onMounted(() => {
  loadWrongBook()
})
</script>

<template>
  <div class="app">
    <header class="header">
      <div class="header-inner">
        <h1 class="logo">AI 教辅智学平台</h1>
        <p class="subtitle">青岛理工大学 AI 应用创新开发大赛 · 教学赋能类</p>
        <div class="nav">
          <button :class="{ active: view === 'home' }" @click="goHome">科目</button>
          <button v-if="wrongBook.length" :class="{ active: view === 'wrong' }" @click="view = 'wrong'">错题本 ({{ wrongBook.length }})</button>
        </div>
      </div>
    </header>

    <main class="main">
      <!-- ======== 科目选择页 ======== -->
      <div v-if="view === 'home'" class="subject-page">
        <h2 class="page-title">选择你想学习的科目</h2>
        <p class="page-desc">选择科目后，可以智能对话答疑，也可以在线自测</p>
        <div class="subject-grid">
          <div v-for="s in subjects" :key="s.id" class="subject-card" :style="{ '--accent': s.color }">
            <div class="subject-icon">{{ s.icon }}</div>
            <div class="subject-name">{{ s.name }}</div>
            <div class="subject-en">{{ s.enName }}</div>
            <div class="subject-desc">{{ s.desc }}</div>
            <div class="subject-actions">
              <button class="action-btn chat-btn" @click="openChat(s)">💬 AI 答疑</button>
              <button class="action-btn quiz-btn" @click="openQuiz(s)">📝 在线自测</button>
              <button class="action-btn kb-btn" @click="openKnowledge(s)">📚 知识库</button>
            </div>
          </div>
        </div>
        <div class="add-tip">新增科目只需在配置中添加知识库与应用即可扩展</div>
        <button class="teacher-entry-btn" @click="view = 'teacher'">📊 教师端 · 智能教学管理</button>
      </div>

      <!-- ======== 教师端（独立组件） ======== -->
      <Teacher v-else-if="view === 'teacher'" @back="goHome" />

      <!-- ======== 错题本 ======== -->
      <div v-else-if="view === 'wrong'" class="wrong-page">
        <div class="page-head">
          <button class="back-btn" @click="goHome">← 返回</button>
          <h2 class="page-title">我的错题本</h2>
        </div>
        <div v-if="!wrongBook.length" class="empty-tip">暂无错题，去自测一下吧！</div>
        <div v-else class="wrong-list">
          <div v-for="w in wrongBook" :key="w.id" class="wrong-card">
            <div class="wrong-tag">{{ w.subject === 'math' ? '高数' : '英语' }} · {{ typeLabels[w.qtype] }}</div>
            <div class="wrong-stem"><MarkdownRender :content="w.stem" /></div>
            <div class="wrong-detail">
              <div class="wrong-answer">正确答案：<span class="correct">{{ w.answer }}</span></div>
              <div v-if="w.analysis" class="wrong-analysis"><strong>解析：</strong><MarkdownRender :content="w.analysis" /></div>
            </div>
            <div class="wrong-foot">
              <span class="kp">知识点：{{ w.knowledge_point }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ======== 知识库页 ======== -->
      <div v-else-if="view === 'kb'" class="kb-page">
        <div class="page-head">
          <button class="back-btn" @click="goHome">← 返回</button>
          <h2 class="page-title">{{ kbSubject.name }} · 知识库</h2>
          <div class="kb-search-bar inline">
            <input v-model="kbSearchQuery" class="chat-input" placeholder="检索知识点…" @keyup.enter="kbSearch" />
            <button class="send-btn" :disabled="kbSearching || !kbSearchQuery.trim()" @click="kbSearch">{{ kbSearching ? '…' : '检索' }}</button>
          </div>
        </div>

        <!-- 检索模式 -->
        <div v-if="kbResults.length" class="wrong-list">
          <h3 class="kb-section-title">检索结果（{{ kbResults.length }}）</h3>
          <div v-for="(r, i) in kbResults" :key="i" class="wrong-card">
            <div class="wrong-tag">相似度 {{ (r.similarity * 100).toFixed(0) }}% · {{ r.document_name }}</div>
            <div class="kb-result-title">{{ r.title }}</div>
            <div class="wrong-stem"><MarkdownRender :content="r.content" /></div>
          </div>
          <button class="back-btn" @click="kbResults = []; kbSearchQuery = ''">← 返回目录</button>
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
            <div class="kb-side-title">{{ kbCurrentDoc ? docDisplayName(kbCurrentDoc.name) : '节' }}（{{ kbSections.length }}）</div>
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
          <button class="back-btn" @click="goHome">←</button>
          <div class="chat-title">
            <span class="chat-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</span>
            <div class="chat-title-text">
              <span class="chat-name">{{ activeSubject.name }} · AI 答疑</span>
              <span class="chat-status"><i class="dot"></i>在线</span>
            </div>
          </div>
          <button class="new-chat-btn" @click="newChat">🔄 新对话</button>
          <div class="chat-model">DeepSeek</div>
        </div>

        <div ref="chatBodyRef" class="chat-body">
          <!-- 欢迎屏 -->
          <div v-if="!messages.length && !chatLoading" class="welcome">
            <div class="welcome-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</div>
            <h3 class="welcome-title">你好，我是{{ activeSubject.name }}AI助教</h3>
            <p class="welcome-desc">基于课程知识库的智能答疑助手，可以问我任何问题</p>
            <div class="quick-chips">
              <button v-for="q in (quickQuestions[activeSubject.id] || [])" :key="q" class="chip" @click="sendQuick(q)">{{ q }}</button>
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

        <div class="chat-input-area">
          <input v-model="input" class="chat-input" placeholder="输入你的问题，回车发送…" @keyup.enter="sendMessage" :disabled="chatLoading" />
          <button class="send-btn" :disabled="chatLoading || !input.trim()" @click="sendMessage">➤</button>
        </div>
      </div>

      <!-- ======== 自测页 ======== -->
      <div v-else-if="view === 'quiz'" class="quiz-page">
        <div class="chat-header">
          <button class="back-btn" @click="goHome">← 返回</button>
          <div class="chat-title">
            <span class="chat-icon" :style="{ background: quizSubject.color }">{{ quizSubject.icon }}</span>
            <span>{{ quizSubject.name }} · 智能自测</span>
          </div>
          <div class="chat-model">{{ quizMode === 'setup' ? '题型选择' : quizMode === 'done' ? '已判卷' : '在线作答' }}</div>
        </div>

        <template v-if="quizMode === 'setup'">
          <div class="quiz-setup">
            <div class="setup-tip">选择本次自测要练习的题型（阅读按"篇"抽题，每篇含 5 道真题）</div>
            <div class="setup-list">
              <div v-for="t in quizConfig" :key="t.kp" class="setup-row" :class="{ on: t.enabled }">
                <label class="setup-toggle">
                  <input type="checkbox" v-model="t.enabled" />
                  <span class="setup-name">{{ t.label }}</span>
                  <span class="setup-count">{{ t.kp === '阅读' ? '真题 ' + (t.max * 5) + ' 题' : '共 ' + t.max + ' 题' }}</span>
                </label>
                <div v-if="t.enabled" class="setup-stepper">
                  <button class="step-btn" @click="t.count > 1 && t.count--">−</button>
                  <span class="step-val">{{ t.count }} {{ t.unit }}</span>
                  <button class="step-btn" @click="t.count < t.max && t.count++">+</button>
                </div>
              </div>
            </div>
            <div class="quiz-submit-bar">
              <button class="send-btn" @click="beginQuiz">开始自测</button>
            </div>
          </div>
        </template>

        <template v-if="quizMode === 'doing'">
          <div v-if="quizLoading" class="empty-tip">正在智能组卷…</div>
          <div v-else class="quiz-body">
            <div class="quiz-list">
              <template v-for="(q, qi) in quizQuestions" :key="q.id">
                <div v-if="q.passage && (qi === 0 || quizQuestions[qi-1].passage !== q.passage)" class="passage-card">
                  <div class="passage-title">📄 阅读理解 · {{ q.passage_key }}</div>
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
                    <span class="opt-text">{{ opt }}</span>
                  </label>
                </div>

                <div v-if="q.qtype === 'multiple'" class="quiz-options">
                  <label v-for="opt in (q.options || [])" :key="opt" class="opt-item" :class="{ selected: quizAnswers[multiKey(q.id)] && quizAnswers[multiKey(q.id)].includes(opt[0]) }">
                    <input type="checkbox" :value="opt[0]" :checked="quizAnswers[multiKey(q.id)] && quizAnswers[multiKey(q.id)].includes(opt[0])"
                      @change="updateMulti(q.id, $event.target.checked, opt)" />
                    <span class="opt-text">{{ opt }}</span>
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
                <label>姓名：</label>
                <input v-model="studentName" class="name-input" placeholder="请输入姓名" />
              </div>
              <button class="send-btn" :disabled="quizLoading" @click="submitQuiz">提交并判卷</button>
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
                  <div class="passage-title">📄 阅读理解 · {{ q.passage_key }}</div>
                  <div class="passage-text"><MarkdownRender :content="q.passage" /></div>
                </div>
                <div class="quiz-card" :class="quizResult.results[q.id]?.correct ? 'correct-card' : 'wrong-card2'">
                <div class="quiz-head">
                  <span class="quiz-num">{{ qi + 1 }}</span>
                  <span class="quiz-type">{{ typeLabels[q.qtype] }}</span>
                  <span class="quiz-mark" :class="quizResult.results[q.id]?.correct ? 'mark-right' : 'mark-wrong'">
                    {{ quizResult.results[q.id]?.correct ? '✓ 正确' : '✗ 错误' }}
                  </span>
                </div>
                <div class="quiz-stem"><MarkdownRender :content="q.stem" /></div>
                <div class="result-detail">
                  <div class="result-line">你的答案：{{ quizResult.results[q.id]?.student_answer || '（未作答）' }}</div>
                  <div v-if="!quizResult.results[q.id]?.correct" class="result-line">正确答案：<span class="correct">{{ quizResult.results[q.id]?.std_answer }}</span></div>
                  <div v-if="quizResult.results[q.id]?.analysis" class="result-line">
                    <strong>解析：</strong><MarkdownRender :content="quizResult.results[q.id]?.analysis" />
                  </div>
                </div>
              </div>
              </template>
            </div>
            <div class="quiz-submit-bar">
              <button class="send-btn" @click="redoQuiz">再来一套</button>
              <button v-if="quizSubject.id === 'english'" class="back-btn" @click="openQuiz(quizSubject)">调整题型</button>
              <button class="back-btn" @click="loadWrongBook(); view = 'wrong'">查看错题本</button>
            </div>
          </div>
        </template>
      </div>
    </main>

    <footer class="footer">AI 教辅智学平台 · 智能教辅双端平台</footer>
  </div>
</template>
