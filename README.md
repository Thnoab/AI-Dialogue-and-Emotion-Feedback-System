# History Management Module

这是张玉韬负责的第三阶段模块，不再维护独立聊天主流程，而是围绕主代码的记忆模块与 SQLite 数据库，提供一个可运行、可演示的历史与记忆管理网页。

## 模块目标

- 读取主代码 `memory` 表中的真实历史记录
- 展示最近对话、较早摘要、emotion 和 history 状态
- 联动主代码记忆接口，验证 `recent context` 是否正常工作
- 作为主系统历史与记忆结果的查看和验证工具

## 默认联动对象

程序启动后会优先尝试读取下面这些默认路径：

- 记忆模块文件：工作区根目录下的 `DS3_Memo.py`
- 若不存在，则回退到工作区根目录下的 `DS2_Memo.py`
- 数据库文件：工作区根目录下的 `Memory_ConverContent.db`

如果你的组长主代码文件或数据库不在这些默认位置，可以通过环境变量指定：

```powershell
$env:DS_MEMORY_MODULE_PATH="实际的 DS3_Memo.py 路径"
$env:DS_MEMORY_DB_PATH="实际的 Memory_ConverContent.db 路径"
```

## 启动方式

推荐使用项目内独立虚拟环境：

```powershell
cd "C:\Users\Administrator\Desktop\对话模型\Large Model AI Conversation"
.\.venv\Scripts\python app.py
```

浏览器访问：

- 模块入口页：`http://127.0.0.1:8000/`
- 历史管理页：`http://127.0.0.1:8000/history`

## 接口列表

- `GET /`：模块入口页
- `GET /history`：历史与记忆管理页
- `GET /memory`：历史与记忆管理页别名
- `GET /api/memory/status`：返回当前主代码模块路径和数据库状态
- `GET /api/memory/all`：读取完整 `memory` 表记录
- `GET /api/memory/latest`：读取最近若干条对话记录
- `GET /api/memory/summaries`：读取较早摘要数据
- `GET /api/memory/context`：读取 recent context
- `GET /api/memory/state`：读取最近 emotion 和 history 状态
- `GET /health`：健康检查

## 当前实现说明

- 如果检测到主代码数据库但没有检测到 `DS3_Memo.py`，页面仍然可以直接读 `memory` 表。
- 如果检测到 `DS3_Memo.py` 且该文件提供 `rappelez` 接口，`recent context` 会优先调用主代码接口。
- 如果数据库文件不存在，页面会明确提示缺少主代码数据库，不再展示你自己的旧 `sessions/messages` 数据。

## 第三阶段演示方式

建议演示顺序如下：

1. 先运行组长主聊天代码并进行若干轮对话
2. 打开你的 `/history` 页面
3. 展示最近对话区确实出现主代码写入的 `submit` 和 `reply`
4. 展示较早摘要区、emotion、history 状态
5. 演示 `recent context` 读取结果，证明你的模块已经联动主系统记忆接口
