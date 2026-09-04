// ============ 个人专属数据层（本地版） ============
// 现阶段：数据存本机 localStorage（按设备隔离）。
// 将来做网站：把本文件的实现换成服务端 API（按账号隔离），函数签名不变，UI 层零改动。
const PREFIX = 'ai-tutor:'

async function read(key, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw ? JSON.parse(raw) : fallback
  } catch (e) {
    return fallback
  }
}

async function write(key, val) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(val))
  } catch (e) {
    console.warn('本地存储失败（可能空间已满）', e)
  }
}

// ============ 聊天记录 ============
export async function loadChatSessions(subjectId) {
  return (await read('chat:' + subjectId, [])).sort((a, b) => b.id - a.id)
}

export async function saveChatSession(subjectId, session) {
  const list = await read('chat:' + subjectId, [])
  const i = list.findIndex(s => s.id === session.id)
  if (i >= 0) list[i] = session
  else list.push(session)
  await write('chat:' + subjectId, list)
}

export async function deleteChatSession(subjectId, sessionId) {
  await write('chat:' + subjectId, (await read('chat:' + subjectId, [])).filter(s => s.id !== sessionId))
}

export async function clearChatSessions(subjectId) {
  await write('chat:' + subjectId, [])
}

// ============ 错题本（个人层） ============
// 结构：{ entries: [个人错题], hiddenDemoIds: [隐藏的示例错题id], demoMastered: {id: bool}, demoNotes: {id: str} }
export async function loadWrongData() {
  return (await read('wrong', { entries: [], hiddenDemoIds: [], demoMastered: {}, demoNotes: {} }))
}

export async function saveWrongData(d) {
  await write('wrong', d)
}

// ============ 学生名单（个人层，教师端） ============
// 结构：{ added: [{name, subject}], renamed: {oldName: newName}, hidden: [name] }
export async function loadStudentOverrides() {
  return (await read('students', { added: [], renamed: {}, hidden: [] }))
}

export async function saveStudentOverrides(d) {
  await write('students', d)
}
