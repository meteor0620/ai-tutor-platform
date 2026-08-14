<script setup>
import { ref, onMounted } from 'vue'
import MarkdownRender from './MarkdownRender.vue'

const emit = defineEmits(['back'])

const SUBJECTS = [
  { id: 'math', name: '高等数学', enName: 'Calculus', color: '#4f46e5', icon: '∫' },
  { id: 'english', name: '大学英语', enName: 'College English', color: '#0d9488', icon: 'A' },
]
const typeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', blank: '填空题', short: '简答题' }
const QTYPE_KEYS = ['single', 'multiple', 'judge', 'blank', 'short']
const TABS = [
  { k: 'dashboard', label: '📊 学情看板' },
  { k: 'students', label: '👨‍🎓 学生' },
  { k: 'bank', label: '📚 题库管理' },
  { k: 'papers', label: '📝 组卷管理' },
  { k: 'knowledge', label: '📖 知识库' },
]

const tab = ref('dashboard')
const subject = ref('math')
const loading = ref(false)
const curSubject = () => SUBJECTS.find(s => s.id === subject.value) || SUBJECTS[0]

function switchSubject(id) {
  subject.value = id
  refreshAll()
}
function switchTab(t) {
  tab.value = t
  refreshAll()
}
function refreshAll() {
  if (tab.value === 'dashboard') loadAnalytics()
  else if (tab.value === 'students') loadStudents()
  else if (tab.value === 'bank') loadBank()
  else if (tab.value === 'papers') loadPapers()
  else loadKbDocs()
}

// ============ 看板 ============
const tOverview = ref(null)
const tKnowledge = ref([])
const tTrends = ref([])
const tWrong = ref([])

async function loadAnalytics() {
  loading.value = true
  try {
    const s = subject.value, base = '/api/analytics'
    const [ov, kn, tr, wr] = await Promise.all([
      fetch(`${base}/overview?subject=${s}`).then(r => r.json()),
      fetch(`${base}/knowledge?subject=${s}`).then(r => r.json()),
      fetch(`${base}/trends?subject=${s}`).then(r => r.json()),
      fetch(`${base}/wrong?subject=${s}`).then(r => r.json()),
    ])
    tOverview.value = ov
    tKnowledge.value = kn.items || []
    tTrends.value = tr.items || []
    tWrong.value = wr.items || []
  } catch (e) { tOverview.value = null }
  loading.value = false
}
function kpColor(acc) { return acc >= 80 ? '#10b981' : acc >= 60 ? '#f59e0b' : '#ef4444' }
function maxWrong() { return Math.max(1, ...tWrong.value.map(w => w.count)) }

// ============ 学生 ============
const students = ref([])
const detail = ref(null)
const detailLoading = ref(false)
const reportLoading = ref(false)

async function loadStudents() {
  loading.value = true
  try {
    const res = await fetch(`/api/analytics/students?subject=${subject.value}`)
    const d = await res.json()
    students.value = d.items || []
  } catch (e) { students.value = [] }
  loading.value = false
}
async function openStudent(name) {
  detailLoading.value = true
  detail.value = { student_name: name, attempts: [], knowledge: [], wrong: [], report: '', reportTime: '', reportCached: false, reportError: '' }
  try {
    const res = await fetch(`/api/analytics/students/${encodeURIComponent(name)}/detail?subject=${subject.value}`)
    detail.value = Object.assign(detail.value, await res.json())
  } catch (e) { detail.value.reportError = '加载失败' }
  detailLoading.value = false
}
function closeDetail() { detail.value = null }
async function genReport(refresh) {
  if (!detail.value) return
  reportLoading.value = true
  detail.value.reportError = ''
  try {
    const res = await fetch('/api/analytics/report', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: subject.value, student_name: detail.value.student_name, refresh: !!refresh }),
    })
    const d = await res.json()
    detail.value.report = d.content || ''
    detail.value.reportTime = d.create_time || ''
    detail.value.reportCached = !!d.cached
  } catch (e) { detail.value.reportError = '生成失败：' + e.message }
  reportLoading.value = false
}

// ============ 题库 ============
const bankItems = ref([])
const bankTotal = ref(0)
const bankPage = ref(1)
const bankSize = 20
const bankFilter = ref({ qtype: '', kp: '' })
const bankStats = ref({})
const bankLoading = ref(false)
const bankModal = ref(null)   // { mode:'add'|'edit', q:{...} }
const bankSaving = ref(false)
const qOptionsText = ref('')  // 弹窗里选项的文本输入（每行一个选项）
const genModal = ref(null)

async function loadBank(resetPage = false) {
  if (resetPage) bankPage.value = 1
  bankLoading.value = true
  try {
    const s = subject.value
    const q = new URLSearchParams({ subject: s, size: bankSize, page: bankPage.value })
    if (bankFilter.value.qtype) q.set('qtype', bankFilter.value.qtype)
    if (bankFilter.value.kp) q.set('knowledge_point', bankFilter.value.kp)
    const [lst, st] = await Promise.all([
      fetch(`/api/questions?${q}`).then(r => r.json()),
      fetch(`/api/questions/stats?subject=${s}`).then(r => r.json()),
    ])
    bankItems.value = lst.items || []
    bankTotal.value = lst.total || 0
    bankStats.value = st.items || {}
  } catch (e) { bankItems.value = [] }
  bankLoading.value = false
}
function openAdd() {
  bankModal.value = { mode: 'add', q: { subject: subject.value, knowledge_point: '', qtype: 'single', difficulty: 'medium', stem: '', answer: '', analysis: '' } }
  qOptionsText.value = ''
}
function openEdit(q) {
  bankModal.value = { mode: 'edit', q: { ...q } }
  qOptionsText.value = (q.options || []).join('\n')
}
function closeBankModal() { bankModal.value = null }
async function saveQuestion() {
  const m = bankModal.value, q = m.q
  if (!q.stem.trim() || !q.answer.trim()) { alert('题干和答案必填'); return }
  bankSaving.value = true
  try {
    const body = {
      subject: q.subject, knowledge_point: q.knowledge_point, qtype: q.qtype,
      difficulty: q.difficulty, stem: q.stem,
      options: (q.qtype === 'single' || q.qtype === 'multiple')
        ? qOptionsText.value.split('\n').map(s => s.trim()).filter(Boolean)
        : [],
      answer: q.answer, analysis: q.analysis || '',
    }
    if (m.mode === 'add') {
      await fetch('/api/questions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    } else {
      await fetch(`/api/questions/${q.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    }
    bankModal.value = null
    loadBank()
  } catch (e) { alert('保存失败：' + e.message) }
  bankSaving.value = false
}
async function deleteQuestion(q) {
  if (!confirm(`确定删除第 ${q.id} 题（${(q.stem || '').slice(0, 20)}…）吗？`)) return
  try { await fetch(`/api/questions/${q.id}`, { method: 'DELETE' }); loadBank() } catch (e) {}
}
function openGen() {
  genModal.value = { subject: subject.value, knowledge_point: '', qtype: 'single', count: 5 }
}
function closeGenModal() { genModal.value = null }
async function runGen() {
  const g = genModal.value
  if (!g.knowledge_point.trim()) { alert('请填写知识点'); return }
  try {
    const res = await fetch('/api/questions/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(g),
    })
    const d = await res.json()
    alert(`已生成 ${d.created || 0} 道题`)
    genModal.value = null
    loadBank()
  } catch (e) { alert('生成失败：' + e.message) }
}

// ============ 组卷 ============
const papers = ref([])
const paperForm = ref({ title: '', single: 3, multiple: 0, judge: 1, blank: 1, short: 0 })
const paperPreview = ref(null)

async function loadPapers() {
  loading.value = true
  try {
    const res = await fetch(`/api/papers?subject=${subject.value}`)
    const d = await res.json()
    papers.value = d.items || []
  } catch (e) { papers.value = [] }
  loading.value = false
}
async function createPaper() {
  const f = paperForm.value
  const counts = {}
  for (const k of QTYPE_KEYS) if (f[k] > 0) counts[k] = f[k]
  if (!Object.keys(counts).length) { alert('请至少选择一种题型'); return }
  try {
    const res = await fetch('/api/papers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: subject.value, title: f.title.trim() || `${curSubject().name}教师组卷`, counts }),
    })
    const d = await res.json()
    if (d.code === 200) { alert(`组卷成功（${d.question_count} 题）`); f.title = ''; loadPapers() }
    else alert('组卷失败：' + (d.detail || '题库暂无题目'))
  } catch (e) { alert('组卷失败：' + e.message) }
}
async function previewPaper(p) {
  try {
    const res = await fetch(`/api/papers/${p.id}?with_answers=1`)
    paperPreview.value = await res.json()
  } catch (e) { alert('预览失败') }
}
function closePreview() { paperPreview.value = null }
async function deletePaper(p) {
  if (!confirm(`确定删除试卷《${p.title}》吗？`)) return
  try { await fetch(`/api/papers/${p.id}`, { method: 'DELETE' }); loadPapers() } catch (e) {}
}

// ============ 知识库（只读浏览 + 检索） ============
const kbDocs = ref([])
const kbSections = ref([])
const kbCurrentDoc = ref(null)
const kbCurrentSection = ref(null)
const kbQuery = ref('')
const kbResults = ref([])

function docDisplayName(name) { return (name || '').replace(/^微积分(?:笔记)?-\d+-/, '') }
async function loadKbDocs() {
  try {
    const res = await fetch(`/api/knowledge/${subject.value}/documents`)
    const d = await res.json()
    kbDocs.value = d.items || []
    kbSections.value = []
    kbCurrentDoc.value = null
    kbCurrentSection.value = null
    kbResults.value = []
    if (kbDocs.value.length) openDoc(kbDocs.value[0])
  } catch (e) { kbDocs.value = [] }
}
async function openDoc(doc) {
  kbCurrentDoc.value = doc
  kbSections.value = []
  kbCurrentSection.value = null
  kbResults.value = []
  try {
    const res = await fetch(`/api/knowledge/${subject.value}/documents/${doc.id}/sections`)
    const d = await res.json()
    kbSections.value = d.items || []
    if (kbSections.value.length) kbCurrentSection.value = kbSections.value[0]
  } catch (e) {}
}
function selectSection(sec) { kbCurrentSection.value = sec }
async function kbSearch() {
  const q = kbQuery.value.trim()
  if (!q) return
  try {
    const res = await fetch(`/api/knowledge/${subject.value}/search`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: subject.value, query: q, top_n: 5 }),
    })
    const d = await res.json()
    kbResults.value = d.items || []
  } catch (e) { kbResults.value = [] }
}

onMounted(() => { loadAnalytics() })
</script>

<template>
  <div class="t-page">
    <div class="page-head">
      <button class="back-btn" @click="emit('back')">← 返回</button>
      <h2 class="page-title">教师端 · 智能教学管理</h2>
      <div class="teacher-subject-tabs">
        <button v-for="s in SUBJECTS" :key="s.id" :class="{ active: subject === s.id }" @click="switchSubject(s.id)">{{ s.name }}</button>
      </div>
    </div>

    <div class="t-tabs">
      <button v-for="t in TABS" :key="t.k" :class="{ active: tab === t.k }" @click="switchTab(t.k)">{{ t.label }}</button>
    </div>

    <!-- ============ 看板 ============ -->
    <div v-if="tab === 'dashboard'" class="dash-area">
      <div v-if="loading" class="empty-tip">加载中…</div>
      <div v-else-if="!tOverview || !tOverview.tests" class="empty-tip">该科目暂无测试数据，让学生先自测一下吧</div>
      <template v-else>
        <div class="stat-grid">
          <div class="stat-card"><div class="stat-num">{{ tOverview.tests }}</div><div class="stat-label">测试次数</div></div>
          <div class="stat-card"><div class="stat-num">{{ tOverview.students }}</div><div class="stat-label">学生数</div></div>
          <div class="stat-card"><div class="stat-num">{{ tOverview.avg }}</div><div class="stat-label">平均分</div></div>
          <div class="stat-card"><div class="stat-num">{{ tOverview.pass_rate }}%</div><div class="stat-label">及格率</div></div>
          <div class="stat-card"><div class="stat-num">{{ tOverview.accuracy }}%</div><div class="stat-label">总正确率</div></div>
          <div class="stat-card"><div class="stat-num">{{ tOverview.wrong_count }}</div><div class="stat-label">错题数</div></div>
        </div>

        <div class="dash-grid">
          <div class="dash-card">
            <h3 class="dash-title">知识点掌握度</h3>
            <div v-for="k in tKnowledge" :key="k.knowledge_point" class="kp-row">
              <div class="kp-name">{{ k.knowledge_point }}</div>
              <div class="kp-bar-wrap">
                <div class="kp-bar" :style="{ width: k.accuracy + '%', background: kpColor(k.accuracy) }"></div>
              </div>
              <div class="kp-val">{{ k.accuracy }}%</div>
            </div>
          </div>

          <div class="dash-card">
            <h3 class="dash-title">错题知识点分布</h3>
            <div v-for="w in tWrong" :key="w.knowledge_point" class="kp-row">
              <div class="kp-name">{{ w.knowledge_point }}</div>
              <div class="kp-bar-wrap">
                <div class="kp-bar wrong-bar2" :style="{ width: (w.count / maxWrong() * 100) + '%' }"></div>
              </div>
              <div class="kp-val">{{ w.count }}</div>
            </div>
          </div>

          <div class="dash-card trend-card">
            <h3 class="dash-title">班级平均分趋势</h3>
            <div class="trend-bars">
              <div v-for="t in tTrends" :key="t.date" class="trend-col">
                <div class="trend-bar" :style="{ height: Math.max(4, t.avg_score) + '%' }" :title="t.date + ' 平均 ' + t.avg_score"></div>
                <div class="trend-date">{{ t.date.slice(5) }}</div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ============ 学生 ============ -->
    <div v-else-if="tab === 'students'" class="stu-area">
      <!-- 学生详情 -->
      <div v-if="detail" class="stu-detail">
        <div class="stu-detail-head">
          <button class="back-btn" @click="closeDetail">← 学生列表</button>
          <h3 class="dash-title">{{ detail.student_name }} · 学习详情（{{ curSubject().name }}）</h3>
        </div>
        <div v-if="detailLoading" class="empty-tip">加载中…</div>
        <template v-else>
          <div class="dash-card report-card">
            <div class="report-head">
              <h3 class="dash-title">🤖 AI 个性化诊断报告</h3>
              <button class="send-btn t-report-btn" :disabled="reportLoading" @click="genReport(false)">{{ reportLoading ? '生成中…' : (detail.report ? '重新生成' : '生成 AI 诊断报告') }}</button>
            </div>
            <div v-if="detail.reportError" class="report-error">{{ detail.reportError }}</div>
            <div v-if="reportLoading" class="empty-tip">正在分析学情并生成报告（约 10-20 秒）…</div>
            <div v-else-if="detail.report" class="report-body">
              <MarkdownRender :content="detail.report" />
              <div class="report-meta">生成时间：{{ detail.reportTime }}<template v-if="detail.reportCached">（缓存）</template></div>
            </div>
            <div v-else class="empty-tip">点击按钮，基于该生历次自测与错题数据生成个性化学习建议</div>
          </div>

          <div class="dash-grid">
            <div class="dash-card">
              <h3 class="dash-title">历次自测成绩</h3>
              <div v-if="!detail.attempts.length" class="empty-tip">暂无自测记录</div>
              <table v-else class="t-table">
                <thead><tr><th>时间</th><th>得分</th><th>正确/总</th></tr></thead>
                <tbody>
                  <tr v-for="a in detail.attempts" :key="a.attempt_id">
                    <td>{{ a.create_time }}</td>
                    <td :class="a.score >= 60 ? 'c-pass' : 'c-fail'">{{ a.score }}</td>
                    <td>{{ a.correct }}/{{ a.total_q }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="dash-card">
              <h3 class="dash-title">知识点掌握度</h3>
              <div v-if="!detail.knowledge.length" class="empty-tip">暂无数据</div>
              <div v-for="k in detail.knowledge" :key="k.knowledge_point" class="kp-row">
                <div class="kp-name">{{ k.knowledge_point }}</div>
                <div class="kp-bar-wrap">
                  <div class="kp-bar" :style="{ width: k.accuracy + '%', background: kpColor(k.accuracy) }"></div>
                </div>
                <div class="kp-val">{{ k.accuracy }}%</div>
              </div>
            </div>
          </div>

          <div class="dash-card">
            <h3 class="dash-title">错题清单（{{ detail.wrong.length }}）</h3>
            <div v-if="!detail.wrong.length" class="empty-tip">该生暂无错题</div>
            <div v-for="w in detail.wrong" :key="w.id" class="wrong-card">
              <div class="wrong-tag">{{ typeLabels[w.qtype] }} · {{ w.knowledge_point }}</div>
              <div class="wrong-stem"><MarkdownRender :content="w.stem" /></div>
              <div class="wrong-detail">
                <div class="wrong-answer">正确答案：<span class="correct">{{ w.answer }}</span></div>
                <div v-if="w.analysis" class="wrong-analysis"><strong>解析：</strong><MarkdownRender :content="w.analysis" /></div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 学生列表 -->
      <div v-else>
        <div v-if="loading" class="empty-tip">加载中…</div>
        <div v-else-if="!students.length" class="empty-tip">该科目暂无学生数据，让学生先自测一下吧</div>
        <div v-else class="stu-grid">
          <div v-for="s in students" :key="s.student_name" class="stu-card" @click="openStudent(s.student_name)">
            <div class="stu-name">{{ s.student_name }}</div>
            <div class="stu-meta">
              <span>测试 {{ s.tests }} 次</span>
              <span>平均 {{ s.avg }} 分</span>
              <span :class="s.latest_score >= 60 ? 'c-pass' : 'c-fail'">最近 {{ s.latest_score }} 分</span>
              <span class="c-fail">错题 {{ s.wrong_count }}</span>
            </div>
            <div class="stu-link">查看详情与 AI 诊断 →</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ 题库 ============ -->
    <div v-else-if="tab === 'bank'" class="bank-area">
      <div class="bank-toolbar">
        <div class="bank-stats">
          <div class="stat-card mini"><div class="stat-num">{{ bankStats[subject]?.total || 0 }}</div><div class="stat-label">总题数</div></div>
          <div v-for="t in QTYPE_KEYS" :key="t" class="stat-card mini">
            <div class="stat-num">{{ bankStats[subject]?.[t] || 0 }}</div><div class="stat-label">{{ typeLabels[t] }}</div>
          </div>
        </div>
        <div class="bank-actions">
          <input v-model="bankFilter.kp" class="chat-input t-filter" placeholder="按知识点筛选" @keyup.enter="loadBank(true)" />
          <select v-model="bankFilter.qtype" class="t-select" @change="loadBank(true)">
            <option value="">全部题型</option>
            <option v-for="t in QTYPE_KEYS" :key="t" :value="t">{{ typeLabels[t] }}</option>
          </select>
          <button class="send-btn" @click="openAdd">＋ 新增题目</button>
          <button class="send-btn t-ai-btn" @click="openGen">✨ AI 批量生成</button>
        </div>
      </div>

      <div v-if="bankLoading" class="empty-tip">加载中…</div>
      <div v-else-if="!bankItems.length" class="empty-tip">该科目题库暂无题目，点右上角新增或 AI 生成</div>
      <div v-else class="bank-list">
        <div v-for="q in bankItems" :key="q.id" class="wrong-card bank-card">
          <div class="wrong-tag">
            #{{ q.id }} · {{ typeLabels[q.qtype] }} · {{ q.difficulty }} · {{ q.knowledge_point }}
            <span class="t-badge">{{ q.source === 'ai' ? 'AI生成' : q.source === 'real' ? '真题' : '手动' }}</span>
          </div>
          <div class="wrong-stem"><MarkdownRender :content="q.stem" /></div>
          <div v-if="(q.options || []).length" class="bank-options">
            <span v-for="o in q.options" :key="o" class="bank-opt" :class="{ 'bank-opt-correct': o.startsWith(q.answer) }">{{ o }}</span>
          </div>
          <div class="wrong-detail">
            <div class="wrong-answer">答案：<span class="correct">{{ q.answer }}</span></div>
            <div v-if="q.analysis" class="wrong-analysis"><strong>解析：</strong><MarkdownRender :content="q.analysis" /></div>
          </div>
          <div class="bank-ops">
            <button class="back-btn" @click="openEdit(q)">编辑</button>
            <button class="back-btn t-del-btn" @click="deleteQuestion(q)">删除</button>
          </div>
        </div>
        <div class="bank-page">
          <span>共 {{ bankTotal }} 题 · 第 {{ bankPage }} 页</span>
          <button class="back-btn" :disabled="bankPage <= 1" @click="bankPage--; loadBank()">上一页</button>
          <button class="back-btn" :disabled="bankPage * bankSize >= bankTotal" @click="bankPage++; loadBank()">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ 组卷 ============ -->
    <div v-else-if="tab === 'papers'" class="paper-area">
      <div class="dash-card paper-create">
        <h3 class="dash-title">新建试卷（{{ curSubject().name }}）</h3>
        <div class="paper-form">
          <label class="t-label">标题</label>
          <input v-model="paperForm.title" class="chat-input" placeholder="如：高数期末模拟卷（留空自动命名）" />
          <div class="paper-counts">
            <label v-for="t in QTYPE_KEYS" :key="t" class="paper-count">
              <span>{{ typeLabels[t] }}</span>
              <input v-model.number="paperForm[t]" type="number" min="0" max="20" class="t-num" />
            </label>
          </div>
          <button class="send-btn" @click="createPaper">组卷</button>
        </div>
      </div>

      <div class="dash-card">
        <h3 class="dash-title">已有试卷（{{ papers.length }}）</h3>
        <div v-if="!papers.length" class="empty-tip">暂无试卷，先在上面组一份吧</div>
        <div v-else class="paper-list">
          <div v-for="p in papers" :key="p.id" class="paper-row">
            <div class="paper-info">
              <div class="paper-title">{{ p.title }}</div>
              <div class="paper-sub">{{ p.create_time }} · {{ p.q_count }} 题</div>
            </div>
            <div class="paper-ops">
              <button class="send-btn" @click="previewPaper(p)">预览</button>
              <button class="back-btn t-del-btn" @click="deletePaper(p)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 试卷预览（带答案） -->
    <div v-if="paperPreview" class="t-modal-overlay" @click.self="closePreview">
      <div class="t-modal t-modal-wide">
        <div class="report-head">
          <h3 class="dash-title">📄 {{ paperPreview.paper?.title }}（教师预览 · 含答案）</h3>
          <button class="back-btn" @click="closePreview">关闭预览</button>
        </div>
        <div class="preview-body">
          <div v-for="(q, qi) in paperPreview.questions" :key="q.id" class="wrong-card bank-card">
            <div class="wrong-tag">
              {{ qi + 1 }} · {{ typeLabels[q.qtype] }} · {{ q.knowledge_point }}
              <span v-if="q.qtype === 'short'" class="t-badge">AI 判分</span>
            </div>
            <div class="wrong-stem"><MarkdownRender :content="q.stem" /></div>
            <div v-if="(q.options || []).length" class="bank-options">
              <span v-for="o in q.options" :key="o" class="bank-opt" :class="{ 'bank-opt-correct': o.startsWith(q.answer) }">{{ o }}</span>
            </div>
            <div class="wrong-detail">
              <div class="wrong-answer">标准答案：<span class="correct">{{ q.answer }}</span></div>
              <div v-if="q.analysis" class="wrong-analysis"><strong>解析：</strong><MarkdownRender :content="q.analysis" /></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ 知识库 ============ -->
    <div v-else class="kb-area">
      <div class="page-head kb-inline">
        <div class="kb-search-bar inline">
          <input v-model="kbQuery" class="chat-input" placeholder="检索知识点…" @keyup.enter="kbSearch" />
          <button class="send-btn" :disabled="!kbQuery.trim()" @click="kbSearch">检索</button>
        </div>
      </div>
      <div v-if="kbResults.length" class="wrong-list">
        <h3 class="kb-section-title">检索结果（{{ kbResults.length }}）</h3>
        <div v-for="(r, i) in kbResults" :key="i" class="wrong-card">
          <div class="wrong-tag">相似度 {{ (r.similarity * 100).toFixed(0) }}% · {{ r.document_name }}</div>
          <div class="kb-result-title">{{ r.title }}</div>
          <div class="wrong-stem"><MarkdownRender :content="r.content" /></div>
        </div>
        <button class="back-btn" @click="kbResults = []; kbQuery = ''">← 返回目录</button>
      </div>
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

    <!-- 新增/编辑题目弹窗 -->
    <div v-if="bankModal" class="t-modal-overlay" @click.self="closeBankModal">
      <div class="t-modal">
        <div class="report-head">
          <h3 class="dash-title">{{ bankModal.mode === 'add' ? '＋ 新增题目' : '✏️ 编辑题目 #' + bankModal.q.id }}</h3>
          <button class="back-btn" @click="closeBankModal">取消</button>
        </div>
        <div class="q-form">
          <div class="q-row">
            <label class="t-label">科目</label>
            <select v-model="bankModal.q.subject" class="t-select">
              <option v-for="s in SUBJECTS" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <label class="t-label">题型</label>
            <select v-model="bankModal.q.qtype" class="t-select">
              <option v-for="t in QTYPE_KEYS" :key="t" :value="t">{{ typeLabels[t] }}</option>
            </select>
            <label class="t-label">难度</label>
            <select v-model="bankModal.q.difficulty" class="t-select">
              <option value="easy">简单</option>
              <option value="medium">中等</option>
              <option value="hard">困难</option>
            </select>
          </div>
          <label class="t-label">知识点</label>
          <input v-model="bankModal.q.knowledge_point" class="chat-input" placeholder="如：极限 / 多元函数 / 词汇" />
          <label class="t-label">题干</label>
          <textarea v-model="bankModal.q.stem" class="t-textarea" rows="3" placeholder="题目内容，支持 LaTeX（如 $\int_0^1 x\,dx$）"></textarea>
          <template v-if="bankModal.q.qtype === 'single' || bankModal.q.qtype === 'multiple'">
            <label class="t-label">选项（每行一个，如 A. xxx）</label>
            <textarea v-model="qOptionsText" class="t-textarea" rows="4" placeholder="A. xxx&#10;B. xxx&#10;C. xxx&#10;D. xxx"></textarea>
          </template>
          <label class="t-label">答案</label>
          <input v-model="bankModal.q.answer" class="chat-input"
            :placeholder="bankModal.q.qtype === 'judge' ? '对 或 错' : (bankModal.q.qtype === 'single' ? '如：A' : (bankModal.q.qtype === 'multiple' ? '如：ABD' : '正确答案文本'))" />
          <label class="t-label">解析</label>
          <textarea v-model="bankModal.q.analysis" class="t-textarea" rows="3" placeholder="（可选）答案解析"></textarea>
          <div class="bank-ops">
            <button class="send-btn" :disabled="bankSaving" @click="saveQuestion">{{ bankSaving ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- AI 批量生成弹窗 -->
    <div v-if="genModal" class="t-modal-overlay" @click.self="closeGenModal">
      <div class="t-modal">
        <div class="report-head">
          <h3 class="dash-title">✨ AI 批量生成题目</h3>
          <button class="back-btn" @click="closeGenModal">取消</button>
        </div>
        <div class="q-form">
          <div class="q-row">
            <label class="t-label">科目</label>
            <select v-model="genModal.subject" class="t-select">
              <option v-for="s in SUBJECTS" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <label class="t-label">题型</label>
            <select v-model="genModal.qtype" class="t-select">
              <option v-for="t in QTYPE_KEYS" :key="t" :value="t">{{ typeLabels[t] }}</option>
            </select>
          </div>
          <label class="t-label">知识点</label>
          <input v-model="genModal.knowledge_point" class="chat-input" placeholder="如：多元函数极值 / 虚拟语气" />
          <label class="t-label">生成数量（1-10）</label>
          <input v-model.number="genModal.count" type="number" min="1" max="10" class="t-num" />
          <div class="bank-ops">
            <button class="send-btn t-ai-btn" @click="runGen">开始生成</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
