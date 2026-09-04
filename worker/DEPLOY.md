# Cloudflare Worker 部署（一次 10 分钟，免费）

## 1. 注册
https://dash.cloudflare.com/sign-up 注册免费账号（不需要信用卡）。

## 2. 创建 Worker
控制台 → Workers & Pages → Create → Worker → 随便起名（如 `ai-tutor-llm`）→ Deploy。

## 3. 粘贴代码
Edit code → 把本目录 `worker.js` 的内容全量粘进去 → Deploy。

## 4. 配置密钥
Worker → Settings → Variables and Secrets → Add：
- Type: **Secret**，Name: `DEEPSEEK_KEY`，Value: DeepSeek 的 API Key（`后端\.env` 里的那个）
- （可选）`DEEPSEEK_MODEL`，默认 `deepseek-chat`

## 5. 记下地址
Worker 页面会给出形如 `https://ai-tutor-llm.<你的子域>.workers.dev` 的地址。

## 6. 填到前端
GitHub 仓库 → Settings → Secrets and variables → Actions → Variables 页签：
- Name: `LLM_PROXY_URL`，Value: `https://ai-tutor-llm.<你的子域>.workers.dev`

GitHub Actions 构建时会自动把它注入为 `VITE_LLM_PROXY`。
不配置也能部署，只是公网版 AI 答疑/简答题 AI 判分不可用（页面有友好提示）。

## 免费额度
每天 10 万次请求，个人演示绰绰有余。
