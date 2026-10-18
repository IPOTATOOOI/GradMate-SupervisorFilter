# GradMate

GradMate 是一个面向研究生申请场景的开源工作台，提供学生画像、导师资料抽取与匹配、招生资料问答、申请邮件、简历辅助、保研 DDL 和可选题库练习等功能。

## 技术栈

- 前端：Vue 3、Vite、Lucide Vue
- 后端：FastAPI、Pydantic、LangChain、SQLite
- 可选集成：OpenAI-compatible / 火山方舟模型、SMTP、Selenium、Neo4j
- 文档处理：PyPDF、python-docx、openpyxl

## 目录结构

```text
GradMate/
├─ backend/
│  ├─ app.py                 # FastAPI 入口与主要 API
│  ├─ agent_runtime.py       # Agent 工具与申请任务编排
│  ├─ agent_tools.py         # 资料抽取、匹配、邮件规则
│  ├─ *_routes.py            # 邮件、简历、题库路由
│  ├─ storage.py             # SQLite 持久化
│  ├─ schema.sql             # 空数据库结构初始化脚本
│  ├─ system_prompt.md       # Agent 系统提示词
│  ├─ data/                  # 本地运行数据
│  └─ requirements.txt
├─ frontend/
│  ├─ src/AppShell.vue       # 主工作台页面
│  ├─ src/styles.css
│  └─ package.json
├─ .env.example              # 环境变量模板
└─ GradMate_软科Top40计算机院系官网.xlsx  # 公共院系官网索引
```

## 环境要求

- Python 3.10+
- Node.js 20.19+（或 22.12+）
- npm 10+

模型、SMTP、Neo4j 和 Selenium 浏览能力都是可选项。

## 配置

在项目根目录复制环境模板：

```powershell
Copy-Item .env.example .env
```

按需编辑 `.env`。不要提交真实的 API Key、邮箱授权码或数据库密码；`.env` 已在 `.gitignore` 中忽略。

模型可任选一种配置方式：

```env
# 火山方舟
ARK_API_KEY=
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
MODEL_ID=

# 或其他 OpenAI-compatible 服务
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=
```

邮件发送需配置 `SMTP_*` 并显式设置 `EMAIL_SEND_ENABLED=true`，题库练习需配置 `PRACTICE_NEO4J_*`。浏览器研究默认使用 Selenium Manager 自动匹配驱动；离线环境可通过 `CHROMEDRIVER_PATH` 指定本地驱动。完整配置项见 [.env.example](.env.example)。

## 本地启动

### 1. 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
python backend\app.py
```

后端默认运行在 `http://127.0.0.1:8000`，API 文档位于 `http://127.0.0.1:8000/docs`。首次启动会根据 `backend/schema.sql` 自动创建空的 `backend/data/gradmate.sqlite3`。

### 2. 前端开发服务器

另开终端：

```powershell
Set-Location frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会将 `/api` 请求代理到后端。

### 3. 生产构建

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
python backend\app.py
```

构建完成后，FastAPI 会直接托管 `frontend/dist`，访问 `http://127.0.0.1:8000` 即可。

## 数据与隐私

- 仓库不包含历史业务数据库、用户画像、导师抓取结果、问答历史或生成报告。
- 运行数据写入 `backend/data/`，导出文件写入 `backend/workspace/`，两者均被 Git 忽略。
- 前端不能读取或修改 API Key、SMTP 账号和密码；敏感配置只从服务端环境变量读取。
- SMTP 发送必须由用户在最终预览中明确确认。
- `GET /api/email/config` 只返回服务是否就绪及非敏感连接状态。

## License

[MIT](LICENSE)
