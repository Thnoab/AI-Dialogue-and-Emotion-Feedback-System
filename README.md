# Large Model AI Conversation

这是一个可运行的 AI 对话系统，包含：

- 多轮对话
- 历史会话切换
- SQLite 消息持久化
- 真实大模型接入

## 安装依赖

```bash
pip install fastapi uvicorn
```

## 启动方式

```bash
python app.py
```

浏览器访问：

- 聊天页：`http://127.0.0.1:8000/`
- 历史页：`http://127.0.0.1:8000/history`

## 模型接入

当前支持两种模式：

### 1. DeepSeek 或其他兼容 OpenAI 的云 API

复制 `.env.example` 的变量到你自己的环境里，至少配置：

```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=你的密钥
```

然后启动：

```bash
python app.py
```

### 2. 本地免费 Ollama

先安装并启动 Ollama，然后拉模型，例如：

```bash
ollama pull qwen2.5:7b
```

再配置环境变量：

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen2.5:7b
```

然后启动：

```bash
python app.py
```

## 接口

- `POST /chat`：发送消息并获取模型回复
- `GET /messages`：读取消息历史
- `GET /sessions`：读取会话列表
- `GET /sessions/{session_id}/context`：读取最近上下文
- `GET /health`：健康检查

## 说明

- 如果未配置 `LLM_API_KEY`，云模型调用会直接报错，不再返回模拟回复。
- 如果使用 Ollama，本地模型推理速度取决于你的机器性能。
