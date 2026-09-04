// Cloudflare Worker：DeepSeek LLM 代理（演示版 AI 答疑 / 简答题 AI 判分共用）
// 作用：把 DeepSeek API Key 放在 Worker 环境变量里，前端永不接触密钥。
// 部署：见同目录 DEPLOY.md

const DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: CORS })
    if (request.method !== 'POST') {
      return json({ error: 'method not allowed' }, 405)
    }
    if (!env.DEEPSEEK_KEY) {
      return json({ error: 'worker 未配置 DEEPSEEK_KEY' }, 500)
    }
    let body
    try {
      body = await request.json()
    } catch (e) {
      return json({ error: 'bad json' }, 400)
    }
    const messages = Array.isArray(body.messages) ? body.messages : null
    if (!messages || !messages.length) {
      return json({ error: 'messages required' }, 400)
    }
    // 简单防护：限制消息体大小与轮数
    const payload = JSON.stringify({ messages: messages.slice(-12) })
    if (payload.length > 60000) {
      return json({ error: 'payload too large' }, 413)
    }
    const upstream = await fetch(DEEPSEEK_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + env.DEEPSEEK_KEY,
      },
      body: JSON.stringify({
        model: env.DEEPSEEK_MODEL || 'deepseek-chat',
        messages,
        temperature: typeof body.temperature === 'number' ? body.temperature : 0.4,
        stream: false,
      }),
    })
    if (!upstream.ok) {
      const text = await upstream.text()
      return json({ error: 'upstream ' + upstream.status, detail: text.slice(0, 300) }, 502)
    }
    const data = await upstream.json()
    return json({ content: data.choices?.[0]?.message?.content || '' })
  },
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  })
}
