// ============ 科目注册表（单一事实源） ============
// ★ 加新科目三步（前端零改动生效：首页/教师端/答疑/自测/知识库/判分全部自动出现）：
//   1. 本文件加一条配置
//   2. 后端 rebuild_ids.json 加 "<id>_kb"（可选 "<id>_app"/"<id>_app_token"），
//      questions 表灌题（generate_math_bank.py / build_cet4_bank.py 模式可复用）
//   3. MaxKB 建知识库+应用（rebuild_kb_create.py / rebuild_apps.py），token 填到 accessToken
// 可选字段：
//   quiz            无 quizTypes 科目的默认组卷配置（点自测直接成卷）
//   quizTypes[]     有则点自测先进「题型选择面板」（hidden:true 的题型不展示）
//   gradePreselect  AI 判分模式默认勾选的题型 kp（仅 quizTypes 科目）
//   gradeHint       判分模式顶部提示条文案
//   chatPrompt      demo 模式 LLM 提示词（full 模式走 MaxKB 应用内配置）
export const SUBJECTS = [
  {
    id: 'math',
    name: '高等数学',
    enName: 'Calculus',
    icon: '∫',
    color: '#4f46e5',
    color2: '#8b5cf6',
    desc: '极限连续 · 导数积分 · 多元微积分 · 级数 · 微分方程',
    accessToken: '0d618bef834e1d83',
    quiz: { counts: { single: 3, multiple: 0, judge: 2, blank: 1, short: 1 }, passages: 0 },
    gradeHint: 'AI 判分体验：客观题提交即秒判，错题自动收进错题本',
    chatQuickQuestions: ['泰勒展开是什么？', '导数的定义', '洛必达法则', '定积分怎么算'],
    chatPrompt: {
      system: '你是高校课程AI助教，回答要精炼、结构化、准确。',
      prefix: '请回答用户的问题：{question}\n请根据下面的知识库内容回答问题，只使用与问题最匹配的<data>段落，忽略无关段落。\n回答结构：① 核心思想 ② 公式 ③ 必考点 ④ 易错点 ⑤ 几何直观（如适用）。\n如果知识库没有相关内容，直接说明。\n<data>\n{data}\n</data>',
    },
  },
  {
    id: 'english',
    name: '大学英语',
    enName: 'College English',
    icon: 'A',
    color: '#0d9488',
    color2: '#22d3ee',
    desc: '四级真题 · 词汇语法 · 阅读理解 · 段落翻译',
    accessToken: '420ea5d3a186ed7f',
    quizTypes: [
      { kp: '阅读', label: '阅读理解', unit: '篇文章', max: 5, count: 1, enabled: true },
      { kp: '翻译', label: '段落翻译', unit: '道题', max: 9, count: 1, enabled: true },
      // hidden: 暂无题源/生成逻辑，不展示；补齐题库后删掉 hidden 即可
      { kp: '词汇', label: '核心词汇', unit: '道题', max: 20, count: 5, enabled: false, hidden: true },
      { kp: '语法', label: '语法练习', unit: '道题', max: 15, count: 3, enabled: false, hidden: true },
      { kp: '写作', label: '写作技巧', unit: '道题', max: 10, count: 2, enabled: false, hidden: true },
    ],
    gradePreselect: '翻译',
    gradeHint: 'AI 判分体验：本卷为段落翻译简答题，提交后由 AI 智能评分并给点评',
    chatQuickQuestions: ['解释一下虚拟语气', '定语从句怎么用', '作文常用句型', '高频核心词汇'],
    chatPrompt: {
      system: '你是高校课程AI助教，回答要精炼、结构化、准确。',
      prefix: '请回答用户的问题：{question}\n请根据下面的知识库内容回答问题，只使用与问题最匹配的<data>段落，忽略无关段落。\n回答结构：① 核心要点 ② 词汇/语法/用法 ③ 常见错误 ④ 例句。\n如果知识库没有相关内容，直接说明。\n<data>\n{data}\n</data>',
    },
  },
]

export const getSubject = id => SUBJECTS.find(s => s.id === id) || SUBJECTS[0]
