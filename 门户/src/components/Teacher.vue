<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch, h } from 'vue'
import * as echarts from 'echarts'
import MarkdownRender from './MarkdownRender.vue'
import AppIcon from './AppIcon.vue'
import { message, dialog } from '../naive'
import { loadStudentOverrides, saveStudentOverrides } from '../storage'

const emit = defineEmits(['back'])

const SUBJECTS = [
  { id: 'math', name: '高等数学', enName: 'Calculus', color: '#4f46e5', icon: '∫' },
  { id: 'english', name: '大学英语', enName: 'College English', color: '#0d9488', icon: 'A' },
]
const typeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', blank: '填空题', short: '简答题' }
const QTYPE_KEYS = ['single', 'multiple', 'judge', 'blank', 'short']
// n-select 选项：题型（全部 + 各类）与难度
const qtypeOptions = [{ label: '全部题型', value: '' }, ...QTYPE_KEYS.map(t => ({ label: typeLabels[t], value: t }))]
const subjectOptions = SUBJECTS.map(s => ({ label: s.name, value: s.id }))
const difficultyOptions = [
  { label: '简单', value: 'easy' },
  { label: '中等', value: 'medium' },
  { label: '困难', value: 'hard' },
]
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
    nextTick(renderDashCharts)
  } catch (e) { tOverview.value = null }
  loading.value = false
}
function kpColor(acc) { return acc >= 80 ? '#10b981' : acc >= 60 ? '#f59e0b' : '#ef4444' }
function maxWrong() { return Math.max(1, ...tWrong.value.map(w => w.count)) }

// ============ ECharts 图表 ============
const dashKpEl = ref(null)
const dashWrongEl = ref(null)
const dashTrendEl = ref(null)
const stuRadarEl = ref(null)
const stuTrendEl = ref(null)
let chartInstances = []
let ro = null  // ResizeObserver：容器尺寸变化时兜底重绘（修正初始化量到旧宽度的问题）

function ensureRo() {
  if (ro) return
  ro = new ResizeObserver(entries => {
    entries.forEach(en => {
      const c = chartInstances.find(ci => ci.getDom() === en.target)
      if (c) c.resize()
    })
  })
}
function disposeCharts() {
  if (ro) { try { ro.disconnect() } catch (e) {} ro = null }
  chartInstances.forEach(c => { try { c.dispose() } catch (e) {} })
  chartInstances = []
}
function makeChart(el, option) {
  if (!el) { console.warn('[chart] el 为空'); return null }
  try {
    ensureRo()
    const c = echarts.init(el, 'dark')
    c.setOption(option)
    chartInstances.push(c)
    ro.observe(el)
    return c
  } catch (e) {
    console.error('[chart] init 失败:', e.message)
    if (el) el.textContent = '图表加载失败: ' + (e && e.message || e)
    return null
  }
}
const axisLineStyle = { lineStyle: { color: 'rgba(255,255,255,0.2)' } }
const splitLineStyle = { splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } } }

function renderDashCharts() {
  disposeCharts()
  console.log('[chart] renderDashCharts 调用, kp=', tKnowledge.value.length, 'ref=', !!dashKpEl.value, 'wrongRef=', !!dashWrongEl.value, 'trendRef=', !!dashTrendEl.value)
  // 知识点掌握度 → 横向条形
  if (tKnowledge.value.length && dashKpEl.value) {
    const kps = tKnowledge.value.slice(0, 12)
    makeChart(dashKpEl.value, {
      grid: { left: 100, right: 44, top: 8, bottom: 20 },
      xAxis: { type: 'value', max: 100, ...splitLineStyle, axisLabel: { formatter: '{value}%', color: '#94a3b8' } },
      yAxis: { type: 'category', data: kps.map(k => k.knowledge_point), ...axisLineStyle, axisLabel: { color: '#cbd5e1', fontSize: 12 } },
      series: [{
        type: 'bar', barWidth: 13,
        data: kps.map(k => ({ value: k.accuracy, itemStyle: { color: kpColor(k.accuracy), borderRadius: 6 } })),
        label: { show: true, position: 'right', formatter: '{c}%', color: '#94a3b8' },
      }],
    })
  }
  // 错题分布 → 环形（缩小半径+标签紧贴，避免顶部扇区标签被裁、底部被图例挤压）
  if (tWrong.value.length && dashWrongEl.value) {
    makeChart(dashWrongEl.value, {
      tooltip: { trigger: 'item', formatter: '{b}: {c} 题 ({d}%)' },
      legend: { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 11 }, itemWidth: 12, itemHeight: 10, icon: 'circle' },
      series: [{
        type: 'pie', radius: ['40%', '62%'], center: ['50%', '46%'],
        itemStyle: { borderRadius: 6, borderColor: '#131a2e', borderWidth: 2 },
        label: { formatter: '{b} {d}%', color: '#cbd5e1', fontSize: 11 },
        labelLine: { length: 10, length2: 6, lineStyle: { color: 'rgba(255,255,255,0.3)' } },
        data: tWrong.value.map(w => ({ name: w.knowledge_point, value: w.count })),
      }],
    })
  }
  // 平均分趋势 → 折线
  if (tTrends.value.length && dashTrendEl.value) {
    makeChart(dashTrendEl.value, {
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 22, bottom: 24 },
      xAxis: { type: 'category', data: tTrends.value.map(t => t.date.slice(5)), ...axisLineStyle, axisLabel: { color: '#94a3b8' } },
      yAxis: { type: 'value', ...splitLineStyle, axisLabel: { color: '#94a3b8' } },
      series: [{
        type: 'line', data: tTrends.value.map(t => t.avg_score), smooth: true, symbolSize: 7,
        lineStyle: { width: 3, color: '#818cf8' }, itemStyle: { color: '#a5b4fc' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.35)' }, { offset: 1, color: 'rgba(99,102,241,0)' }] } },
      }],
    })
  }
}

function renderStuCharts() {
  disposeCharts()
  const d = detail.value
  if (!d) return
  // 知识点掌握度 → 雷达
  if (d.knowledge && d.knowledge.length && stuRadarEl.value) {
    const items = d.knowledge.slice(0, 8)
    makeChart(stuRadarEl.value, {
      tooltip: {},
      radar: {
        indicator: items.map(k => ({ name: k.knowledge_point, max: 100 })),
        radius: '64%', center: ['50%', '50%'],
        axisName: { color: '#cbd5e1', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.14)' } },
        splitArea: { areaStyle: { color: ['rgba(99,102,241,0.07)', 'rgba(255,255,255,0.02)'] } },
        ...axisLineStyle,
      },
      series: [{
        type: 'radar',
        data: [{
          value: items.map(k => k.accuracy), name: '掌握度',
          areaStyle: { color: 'rgba(99,102,241,0.35)' },
          lineStyle: { color: '#818cf8', width: 2 }, itemStyle: { color: '#a5b4fc' },
        }],
      }],
    })
  }
  // 历次成绩 → 折线
  if (d.attempts && d.attempts.length && stuTrendEl.value) {
    makeChart(stuTrendEl.value, {
      tooltip: { trigger: 'axis' },
      grid: { left: 36, right: 14, top: 20, bottom: 24 },
      xAxis: { type: 'category', data: d.attempts.map(a => (a.create_time || '').slice(5, 10)), ...axisLineStyle, axisLabel: { color: '#94a3b8' } },
      yAxis: { type: 'value', ...splitLineStyle, axisLabel: { color: '#94a3b8' } },
      series: [{
        type: 'line', data: d.attempts.map(a => a.score), smooth: true, symbolSize: 6,
        lineStyle: { width: 2.5, color: '#2dd4bf' }, itemStyle: { color: '#5eead4' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(45,212,191,0.3)' }, { offset: 1, color: 'rgba(45,212,191,0)' }] } },
      }],
    })
  }
}

onBeforeUnmount(() => {
  disposeCharts()
})

// ============ 学生 ============
const students = ref([])
const detail = ref(null)
const detailLoading = ref(false)
const reportLoading = ref(false)
// ---- 学生名单个人层（本地增删改，将来换服务端按账号存） ----
const stuOverrides = ref({ added: [], renamed: {}, hidden: [] })
const newStuName = ref('')
const stuAdding = ref(false)

async function loadStuOverrides() {
  stuOverrides.value = await loadStudentOverrides()
}

async function persistStuOverrides() {
  await saveStudentOverrides(JSON.parse(JSON.stringify(stuOverrides.value)))
}

function applyStuOverrides(list) {
  // 改名 → 隐藏 → 追加本地新增
  const renamed = list.map(s => {
    const nn = stuOverrides.value.renamed[s.student_name]
    return nn ? { ...s, student_name: nn, demoName: s.student_name, localEdited: true } : s
  }).filter(s => !stuOverrides.value.hidden.includes(s.demoName || s.student_name))
  const exist = new Set(renamed.map(s => s.student_name))
  const added = stuOverrides.value.added
    .filter(a => a.subject === subject.value && !exist.has(a.name))
    .map(a => ({ student_name: a.name, tests: 0, avg: 0, latest_score: 0, wrong_count: 0, localOnly: true }))
  return [...added, ...renamed]
}

async function addStudent() {
  const name = newStuName.value.trim()
  if (!name) return
  if (students.value.some(s => s.student_name === name)) {
    message.warning('已有同名学生')
    return
  }
  stuOverrides.value.added.push({ name, subject: subject.value })
  await persistStuOverrides()
  newStuName.value = ''
  loadStudents()
}

async function renameStudent(s) {
  const nn = prompt('修改学生姓名：', s.student_name)
  if (!nn || nn.trim() === s.student_name) return
  const name = nn.trim()
  if (students.value.some(x => x.student_name === name)) {
    message.warning('已有同名学生')
    return
  }
  // 本地新增的直接改 added；示例数据走改名映射
  const addedItem = stuOverrides.value.added.find(a => a.name === s.student_name)
  if (addedItem) addedItem.name = name
  else stuOverrides.value.renamed[s.demoName || s.student_name] = name
  await persistStuOverrides()
  loadStudents()
}

async function removeStudent(s) {
  if (!confirm(`删除学生「${s.student_name}」？\n（本地新增的学生会被移除；示例数据只是从列表隐藏，不影响原始数据）`)) return
  const idx = stuOverrides.value.added.findIndex(a => a.name === s.student_name)
  if (idx >= 0) stuOverrides.value.added.splice(idx, 1)
  else stuOverrides.value.hidden.push(s.demoName || s.student_name)
  await persistStuOverrides()
  loadStudents()
}

// n-data-table 列定义：历次自测成绩（得分着色保留）
const attemptsColumns = [
  { title: '时间', key: 'create_time' },
  { title: '得分', key: 'score', render: r => h('span', { class: r.score >= 60 ? 'c-pass' : 'c-fail' }, r.score) },
  { title: '正确/总', key: 'correct', render: r => `${r.correct}/${r.total_q}` },
]

async function loadStudents() {
  loading.value = true
  try {
    const res = await fetch(`/api/analytics/students?subject=${subject.value}`)
    const d = await res.json()
    students.value = applyStuOverrides(d.items || [])
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
  nextTick(renderStuCharts)
}
function closeDetail() {
  disposeCharts()
  detail.value = null
}
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
  if (!q.stem.trim() || !q.answer.trim()) { message.error('题干和答案必填'); return }
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
  } catch (e) { message.error('保存失败：' + e.message) }
  bankSaving.value = false
}
async function deleteQuestion(q) {
  dialog.warning({
    title: '删除题目',
    content: `确定删除第 ${q.id} 题（${(q.stem || '').slice(0, 20)}…）吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try { await fetch(`/api/questions/${q.id}`, { method: 'DELETE' }); loadBank() } catch (e) {}
    },
  })
}
function openGen() {
  genModal.value = { subject: subject.value, knowledge_point: '', qtype: 'single', count: 5 }
}
function closeGenModal() { genModal.value = null }
async function runGen() {
  const g = genModal.value
  if (!g.knowledge_point.trim()) { message.error('请填写知识点'); return }
  try {
    const res = await fetch('/api/questions/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(g),
    })
    const d = await res.json()
    message.success(`已生成 ${d.created || 0} 道题`)
    genModal.value = null
    loadBank()
  } catch (e) { message.error('生成失败：' + e.message) }
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
  if (!Object.keys(counts).length) { message.error('请至少选择一种题型'); return }
  try {
    const res = await fetch('/api/papers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: subject.value, title: f.title.trim() || `${curSubject().name}教师组卷`, counts, source: 'teacher' }),
    })
    const d = await res.json()
    if (d.code === 200) { message.success(`组卷成功（${d.question_count} 题）`); f.title = ''; loadPapers() }
    else message.error('组卷失败：' + (d.detail || '题库暂无题目'))
  } catch (e) { message.error('组卷失败：' + e.message) }
}
async function previewPaper(p) {
  try {
    const res = await fetch(`/api/papers/${p.id}?with_answers=1`)
    paperPreview.value = await res.json()
  } catch (e) { message.error('预览失败') }
}
function closePreview() { paperPreview.value = null }
async function deletePaper(p) {
  dialog.warning({
    title: '删除试卷',
    content: `确定删除试卷《${p.title}》吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try { await fetch(`/api/papers/${p.id}`, { method: 'DELETE' }); loadPapers() } catch (e) {}
    },
  })
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

// 数据到位后驱动图表渲染（放在所有声明之后，避免 TDZ）
watch([tKnowledge, tWrong, tTrends], () => { nextTick(renderDashCharts) })
watch(detail, () => { nextTick(renderStuCharts) }, { deep: true })

onMounted(() => { loadStuOverrides(); loadAnalytics() })
</script>

<template>
  <div class="t-page">
    <div class="page-head">
      <n-button quaternary @click="emit('back')">← 返回</n-button>
      <h2 class="page-title">教师端 · 智能教学管理</h2>
      <n-radio-group v-model:value="subject" size="small" @update:value="switchSubject">
        <n-radio-button v-for="s in SUBJECTS" :key="s.id" :value="s.id">{{ s.name }}</n-radio-button>
      </n-radio-group>
    </div>

    <div class="t-tabs">
      <n-radio-group v-model:value="tab" @update:value="switchTab">
        <n-radio-button v-for="t in TABS" :key="t.k" :value="t.k">{{ t.label }}</n-radio-button>
      </n-radio-group>
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
            <div v-if="!tKnowledge.length" class="empty-tip">暂无数据</div>
            <div v-else ref="dashKpEl" class="t-chart"></div>
          </div>

          <div class="dash-card">
            <h3 class="dash-title">错题知识点分布</h3>
            <div v-if="!tWrong.length" class="empty-tip">暂无错题</div>
            <div v-else ref="dashWrongEl" class="t-chart t-chart-donut"></div>
          </div>

          <div class="dash-card trend-card">
            <h3 class="dash-title">班级平均分趋势</h3>
            <div v-if="!tTrends.length" class="empty-tip">暂无趋势数据</div>
            <div v-else ref="dashTrendEl" class="t-chart"></div>
          </div>
        </div>
      </template>
    </div>

    <!-- ============ 学生 ============ -->
    <div v-else-if="tab === 'students'" class="stu-area">
      <!-- 学生详情 -->
      <div v-if="detail" class="stu-detail">
        <div class="stu-detail-head">
          <n-button quaternary class="back-btn" @click="closeDetail"><AppIcon name="back" :size="16" /> 学生列表</n-button>
          <h3 class="dash-title">{{ detail.student_name }} · 学习详情（{{ curSubject().name }}）</h3>
        </div>
        <div v-if="detailLoading" class="empty-tip">加载中…</div>
        <template v-else>
          <div class="dash-card report-card">
            <div class="report-head">
              <h3 class="dash-title">🤖 AI 个性化诊断报告</h3>
              <n-button type="primary" :loading="reportLoading" @click="genReport(false)">{{ detail.report ? '重新生成' : '生成 AI 诊断报告' }}</n-button>
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
              <template v-else>
                <div ref="stuTrendEl" class="t-chart t-chart-sm"></div>
                <n-data-table :data="detail.attempts" :columns="attemptsColumns" :pagination="false" size="small" :bordered="false" :max-height="220" />
              </template>
            </div>

            <div class="dash-card">
              <h3 class="dash-title">知识点掌握度</h3>
              <div v-if="!detail.knowledge.length" class="empty-tip">暂无数据</div>
              <div v-else ref="stuRadarEl" class="t-chart"></div>
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
        <div class="stu-toolbar">
          <div class="stu-add">
            <input v-model="newStuName" class="stu-add-input" placeholder="输入学生姓名" @keyup.enter="addStudent" />
            <n-button type="primary" size="small" :disabled="!newStuName.trim()" @click="addStudent"><AppIcon name="check" :size="14" /> 添加学生</n-button>
          </div>
          <span class="stu-hint">名单保存在本机 · 删除示例学生仅隐藏不删数据</span>
        </div>
        <div v-if="loading" class="empty-tip">加载中…</div>
        <div v-else-if="!students.length" class="empty-tip">该科目暂无学生，可在上方添加，或让学生先自测</div>
        <div v-else class="stu-grid">
          <div v-for="s in students" :key="s.student_name" class="stu-card" @click="openStudent(s.student_name)">
            <div class="stu-ops">
              <button class="op-btn" title="重命名" @click.stop="renameStudent(s)"><AppIcon name="pencil" :size="13" /></button>
              <button class="op-btn danger" title="删除" @click.stop="removeStudent(s)"><AppIcon name="x" :size="13" /></button>
            </div>
            <div class="stu-name">
              {{ s.student_name }}
              <span v-if="s.localOnly" class="demo-tag">本地</span>
              <span v-else-if="s.localEdited" class="demo-tag">已改名</span>
            </div>
            <div v-if="s.localOnly" class="stu-meta"><span>本地名单 · 暂无学习数据</span></div>
            <div v-else class="stu-meta">
              <span>测试 {{ s.tests }} 次</span>
              <span>平均 {{ s.avg }} 分</span>
              <span :class="s.latest_score >= 60 ? 'c-pass' : 'c-fail'">最近 {{ s.latest_score }} 分</span>
              <span class="c-fail">错题 {{ s.wrong_count }}</span>
            </div>
            <div class="stu-link">{{ s.localOnly ? '本地名单学生' : '查看详情与 AI 诊断 →' }}</div>
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
          <n-input v-model:value="bankFilter.kp" placeholder="按知识点筛选" @keyup.enter="loadBank(true)" clearable style="width:170px" />
          <n-select v-model:value="bankFilter.qtype" placeholder="全部题型" style="width:130px" :options="qtypeOptions" @update:value="loadBank(true)" />
          <n-button type="primary" @click="openAdd">＋ 新增题目</n-button>
          <n-button type="success" @click="openGen">✨ AI 批量生成</n-button>
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
            <n-button size="small" @click="openEdit(q)">编辑</n-button>
            <n-button size="small" type="error" @click="deleteQuestion(q)">删除</n-button>
          </div>
        </div>
        <div class="bank-page">
          <n-pagination :item-count="bankTotal" v-model:page="bankPage" :page-size="bankSize" @update:page="loadBank" />
        </div>
      </div>
    </div>

    <!-- ============ 组卷 ============ -->
    <div v-else-if="tab === 'papers'" class="paper-area">
      <div class="dash-card paper-create">
        <h3 class="dash-title">新建试卷（{{ curSubject().name }}）</h3>
        <div class="paper-form">
          <label class="t-label">标题</label>
          <n-input v-model:value="paperForm.title" placeholder="如：高数期末模拟卷（留空自动命名）" />
          <div class="paper-counts">
            <label v-for="t in QTYPE_KEYS" :key="t" class="paper-count">
              <span>{{ typeLabels[t] }}</span>
              <n-input-number v-model:value="paperForm[t]" :min="0" :max="20" style="width:72px" />
            </label>
          </div>
          <n-button type="primary" @click="createPaper">组卷</n-button>
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
              <n-button size="small" type="primary" @click="previewPaper(p)">预览</n-button>
              <n-button size="small" type="error" @click="deletePaper(p)">删除</n-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 试卷预览（带答案） -->
    <n-modal :show="!!paperPreview" preset="card" style="width: 760px" :bordered="false"
      :title="paperPreview ? '📄 ' + (paperPreview.paper?.title || '') + '（教师预览 · 含答案）' : ''"
      @close="closePreview">
      <div v-if="paperPreview" class="preview-body">
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
    </n-modal>

    <!-- ============ 知识库 ============ -->
    <div v-if="tab === 'knowledge'" class="kb-area">
      <div class="page-head kb-inline">
        <div class="kb-search-bar inline">
          <n-input v-model:value="kbQuery" placeholder="检索知识点…" @keyup.enter="kbSearch" clearable />
          <n-button type="primary" :disabled="!kbQuery.trim()" @click="kbSearch">检索</n-button>
        </div>
      </div>
      <div v-if="kbResults.length" class="wrong-list">
        <h3 class="kb-section-title">检索结果（{{ kbResults.length }}）</h3>
        <div v-for="(r, i) in kbResults" :key="i" class="wrong-card">
          <div class="wrong-tag">相似度 {{ (r.similarity * 100).toFixed(0) }}% · {{ r.document_name }}</div>
          <div class="kb-result-title">{{ r.title }}</div>
          <div class="wrong-stem"><MarkdownRender :content="r.content" /></div>
        </div>
        <n-button quaternary @click="kbResults = []; kbQuery = ''">← 返回目录</n-button>
      </div>
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

    <!-- 新增/编辑题目弹窗 -->
    <n-modal :show="!!bankModal" preset="card" style="width: 640px" :bordered="false"
      :title="bankModal ? (bankModal.mode === 'add' ? '＋ 新增题目' : '✏️ 编辑题目 #' + bankModal.q.id) : ''"
      @close="closeBankModal">
      <div v-if="bankModal" class="q-form">
        <div class="q-row">
          <span class="t-label">科目</span>
          <n-select v-model:value="bankModal.q.subject" style="width:110px" :options="subjectOptions" />
          <span class="t-label">题型</span>
          <n-select v-model:value="bankModal.q.qtype" style="width:110px" :options="qtypeOptions.filter(o => o.value !== '')" />
          <span class="t-label">难度</span>
          <n-select v-model:value="bankModal.q.difficulty" style="width:100px" :options="difficultyOptions" />
        </div>
        <label class="t-label">知识点</label>
        <n-input v-model:value="bankModal.q.knowledge_point" placeholder="如：极限 / 多元函数 / 词汇" />
        <label class="t-label">题干</label>
        <n-input v-model:value="bankModal.q.stem" type="textarea" :autosize="{ minRows: 3 }" placeholder="题目内容，支持 LaTeX（如 $\int_0^1 x\,dx$）" />
        <template v-if="bankModal.q.qtype === 'single' || bankModal.q.qtype === 'multiple'">
          <label class="t-label">选项（每行一个，如 A. xxx）</label>
          <n-input v-model:value="qOptionsText" type="textarea" :autosize="{ minRows: 4 }" placeholder="A. xxx&#10;B. xxx&#10;C. xxx&#10;D. xxx" />
        </template>
        <label class="t-label">答案</label>
        <n-input v-model:value="bankModal.q.answer"
          :placeholder="bankModal.q.qtype === 'judge' ? '对 或 错' : (bankModal.q.qtype === 'single' ? '如：A' : (bankModal.q.qtype === 'multiple' ? '如：ABD' : '正确答案文本'))" />
        <label class="t-label">解析</label>
        <n-input v-model:value="bankModal.q.analysis" type="textarea" :autosize="{ minRows: 3 }" placeholder="（可选）答案解析" />
      </div>
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <n-button @click="closeBankModal">取消</n-button>
          <n-button type="primary" :loading="bankSaving" @click="saveQuestion">保存</n-button>
        </div>
      </template>
    </n-modal>

    <!-- AI 批量生成弹窗 -->
    <n-modal :show="!!genModal" preset="card" style="width: 480px" :bordered="false"
      title="✨ AI 批量生成题目" @close="closeGenModal">
      <div v-if="genModal" class="q-form">
        <div class="q-row">
          <span class="t-label">科目</span>
          <n-select v-model:value="genModal.subject" style="width:110px" :options="subjectOptions" />
          <span class="t-label">题型</span>
          <n-select v-model:value="genModal.qtype" style="width:110px" :options="qtypeOptions.filter(o => o.value !== '')" />
        </div>
        <label class="t-label">知识点</label>
        <n-input v-model:value="genModal.knowledge_point" placeholder="如：多元函数极值 / 虚拟语气" />
        <label class="t-label">生成数量（1-10）</label>
        <n-input-number v-model:value="genModal.count" :min="1" :max="10" style="width:120px" />
      </div>
      <template #footer>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <n-button @click="closeGenModal">取消</n-button>
          <n-button type="primary" @click="runGen">开始生成</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
