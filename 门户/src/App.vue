<script setup>
import { ref, onMounted } from 'vue'
import MarkdownRender from './components/MarkdownRender.vue'

const subjects = [
  {
    id: 'math',
    name: '高等数学',
    enName: 'Calculus',
    desc: '函数极限 · 导数微分 · 积分 · 多元函数 · 微分方程',
    accessToken: '81e652b7c938cdcb',
    color: '#4f46e5',
    icon: '∫',
  },
  {
    id: 'english',
    name: '大学英语',
    enName: 'College English',
    desc: '核心词汇 · 语法 · 阅读理解 · 写作技巧',
    accessToken: '4ecd86138bcbf5ec',
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
function openChat(subject) {
  activeSubject.value = subject
  view.value = 'chat'
  messages.value = []
  chatId.value = ''
  chatToken.value = ''
  openSession(subject)
}

async function openSession(subject) {
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
    messages.value.push({ role: 'ai', content: `你好！我是${subject.name}助教，有什么问题尽管问我。` })
  } catch (e) {
    messages.value.push({ role: 'ai', content: '连接失败：' + e.message })
  }
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || chatLoading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  chatLoading.value = true
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
    messages.value.push({ role: 'ai', content: answer })
  } catch (e) {
    messages.value.push({ role: 'ai', content: '请求失败：' + e.message })
  } finally {
    chatLoading.value = false
  }
}

// ============ 自测 ============
function openQuiz(subject) {
  quizSubject.value = subject
  quizMode.value = 'doing'
  quizQuestions.value = []
  quizAnswers.value = {}
  quizResult.value = null
  quizPaperId.value = null
  startQuiz(subject)
}

async function startQuiz(subject) {
  quizLoading.value = true
  try {
    const res = await fetch('/api/papers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject: subject.id,
        title: `${subject.name}智能组卷`,
        counts: quizCounts.value,
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
      </div>

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
      <div v-else-if="view === 'chat'" class="chat-page">
        <div class="chat-header">
          <button class="back-btn" @click="goHome">← 返回</button>
          <div class="chat-title">
            <span class="chat-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</span>
            <span>{{ activeSubject.name }} · AI 答疑</span>
          </div>
          <div class="chat-model">DeepSeek-V4-Flash</div>
        </div>
        <div class="chat-body">
          <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
            <div class="msg-bubble">
              <div v-if="m.role === 'ai'" class="msg-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</div>
              <div class="msg-text"><MarkdownRender :content="m.content" /></div>
            </div>
          </div>
          <div v-if="chatLoading" class="msg-row ai">
            <div class="msg-bubble">
              <div class="msg-icon" :style="{ background: activeSubject.color }">{{ activeSubject.icon }}</div>
              <div class="msg-text typing">正在思考…</div>
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <input v-model="input" class="chat-input" placeholder="输入你的问题…" @keyup.enter="sendMessage" :disabled="chatLoading" />
          <button class="send-btn" :disabled="chatLoading || !input.trim()" @click="sendMessage">发送</button>
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
          <div class="chat-model">{{ quizMode === 'done' ? '已判卷' : '在线作答' }}</div>
        </div>

        <template v-if="quizMode === 'doing'">
          <div v-if="quizLoading" class="empty-tip">正在智能组卷…</div>
          <div v-else class="quiz-body">
            <div class="quiz-list">
              <div v-for="(q, qi) in quizQuestions" :key="q.id" class="quiz-card">
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
                  <textarea v-model="quizAnswers[q.id]" class="short-input" placeholder="请输入你的回答…" rows="4"></textarea>
                </div>
              </div>
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
              <div v-for="(q, qi) in quizQuestions" :key="q.id" class="quiz-card" :class="quizResult.results[q.id]?.correct ? 'correct-card' : 'wrong-card2'">
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
            </div>
            <div class="quiz-submit-bar">
              <button class="send-btn" @click="openQuiz(quizSubject)">再来一套</button>
              <button class="back-btn" @click="loadWrongBook(); view = 'wrong'">查看错题本</button>
            </div>
          </div>
        </template>
      </div>
    </main>

    <footer class="footer">AI 教辅智学平台 · 智能教辅双端平台</footer>
  </div>
</template>
