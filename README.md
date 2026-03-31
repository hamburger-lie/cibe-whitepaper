# CIBE 美业数据白皮书自动生成系统

AI 驱动的行业白皮书自动生成工具，专为 CIBE 广州国际美博会打造。融合文件解析、大模型内容生成、智能数据可视化、AI 配图等能力，支持多格式输入，自动生成专业级行业白皮书。

## 功能特性

- **多格式数据输入** — 支持 CSV / Excel / Word / PDF 文件上传，也支持直接粘贴文本
- **四角色 AI 管线** — 战略官设计大纲 → 主笔撰写正文 + 视觉导演生成配图 → 图表数据官生成可视化
- **智能图表** — ECharts 自动生成可视化图表（柱状图 / 折线图 / 饼图 / 面积图 / 散点图）
- **AI 配图** — 豆包星绘生成高端商业摄影风格配图（可选）
- **PDF 导出** — 高清 A4 格式，封面独立页，一级标题自动分页
- **在线编辑** — 支持正文编辑和图表可视化编辑，实时预览

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    浏览器前端                         │
│          index.html (Marked + ECharts + jsPDF)       │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP API
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI 后端 (proxy.py)              │
│                                                      │
│  ┌──────────┐   ┌───────────────────────────────┐   │
│  │ 文件解析  │   │     四角色 AI 管线              │   │
│  │ CSV/Excel │   │                               │   │
│  │ Word/PDF  │   │  Agent1 战略官 → 结构化大纲     │   │
│  └──────────┘   │       ↓                        │   │
│                  │  Agent2 主笔    (并发)          │   │
│                  │  Agent3 视觉导演 (并发)          │   │
│                  │       ↓                        │   │
│                  │  Agent4 图表数据官 (并发)        │   │
│                  │       ↓                        │   │
│                  │  合并 → 完整白皮书 Markdown      │   │
│                  └───────────────────────────────┘   │
│                                                      │
│  ┌──────────────┐  ┌────────────────┐               │
│  │ DeepSeek API │  │ 豆包星绘 API    │               │
│  │ (文本生成)    │  │ (配图生成,可选) │               │
│  └──────────────┘  └────────────────┘               │
└──────────────────────────────────────────────────────┘
```

### 四角色分工

| 角色 | 职责 | 输出 |
|------|------|------|
| **Agent1 战略官** | 将原始数据设计为白皮书结构化大纲 | JSON 大纲（含章节、数据锚点、图表意图等） |
| **Agent2 主笔** | 撰写各章正文，总-分-总论证结构 | Markdown 正文（1000-1500 字/章） |
| **Agent3 视觉导演** | 将章节场景转化为摄影指令 | 豆包星绘 Prompt |
| **Agent4 图表数据官** | 从正文提炼数据，生成图表配置 | ECharts JSON 配置 |

## 快速启动

### 环境要求

- Python 3.9+
- pip

### 1. 克隆项目

```bash
git clone https://github.com/hamburger-lie/cibe-whitepaper.git
cd cibe-whitepaper
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

依赖列表：
- `fastapi` — Web 框架
- `uvicorn` — ASGI 服务器
- `openai` — DeepSeek API 客户端（OpenAI 兼容）
- `pandas` — CSV/Excel 数据处理
- `python-docx` — Word 文件解析
- `pdfplumber` — PDF 文本提取
- `requests` — HTTP 请求
- `python-multipart` — 文件上传支持
- `python-dotenv` — 环境变量管理

### 3. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 必填 — DeepSeek API 密钥（用于文本生成）
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# 选填 — 豆包星绘 API 密钥（用于 AI 配图，不配置则配图功能不可用）
ARK_API_KEY=your_ark_api_key_here

# 选填 — CORS 允许的来源
ALLOWED_ORIGINS=http://localhost:5678,http://127.0.0.1:5678
```

**获取 API Key：**
- DeepSeek：访问 https://platform.deepseek.com/ 注册并获取
- 豆包星绘：访问 https://www.volcengine.com/product/doubao 开通火山方舟服务

### 4. 启动服务

```bash
python proxy.py
```

启动后会显示：

```
==================================================
  CIBE 美业白皮书生成系统 启动中...
  DeepSeek API: 已配置
  豆包星绘:     已配置
  访问地址: http://localhost:5678
==================================================
```

### 5. 打开浏览器

访问 **http://localhost:5678** 即可使用。

## 使用指南

### 上传数据

系统支持三种输入方式：

1. **文件上传** — 拖拽或点击上传 CSV / Excel / Word / PDF 文件，支持同时上传多个文件
2. **粘贴文本** — 直接粘贴行业数据、调研报告等文本内容
3. **直接输入** — 在文本框中手动输入数据

### 生成白皮书

1. 上传数据后，点击 **"生成白皮书"** 按钮
2. 系统依次执行四个 AI 角色，进度条实时显示
3. 生成完成后，白皮书自动渲染在预览区

### 编辑内容

- 点击 **"编辑模式"** 按钮进入编辑状态
- 直接点击正文内容进行修改
- 点击图表上的编辑按钮，打开可视化图表编辑器：
  - 修改图表类型（柱状图/折线图/饼图等）
  - 编辑标题、标签、数据值
  - 调整颜色配置
  - 实时预览效果

### 导出 PDF

- 点击 **"导出 PDF"** 按钮
- 自动生成 A4 格式 PDF，包含：
  - 封面页（独立页面）
  - 执行摘要、目录、研究说明（各起新页）
  - 正文各章节（一级标题自动分页）
  - 结论与行动建议
  - 参考说明

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/health` | GET | 健康检查，返回 API 配置状态 |
| `/api/generate` | POST | 白皮书生成（上传文件 + 文本） |
| `/api/generate-image` | POST | AI 配图生成 |

### POST /api/generate

**请求：** `multipart/form-data`
- `files` — 上传文件（支持多个）
- `text` — 文本输入（可选）

**响应：**
```json
{
  "status": "success",
  "markdown": "# 白皮书标题\n\n..."
}
```

### POST /api/generate-image

**请求：** `multipart/form-data`
- `prompt` — 图片描述
- `width` — 宽度（默认 768）
- `height` — 高度（默认 512）

**响应：**
```json
{
  "status": "success",
  "image_base64": "..."
}
```

## 文件结构

```
cibe-whitepaper/
├── proxy.py          # 后端服务（FastAPI + 四角色 AI 管线）
├── index.html        # 前端界面（单文件，含 CSS/JS）
├── .env.example      # 环境变量模板
├── .env              # 环境变量配置（需自行创建，不纳入版本控制）
├── .gitignore        # Git 忽略规则
├── requirements.txt  # Python 依赖
└── README.md         # 项目文档
```

## 技术栈

**后端：**
- Python 3.9+ / FastAPI / Uvicorn
- DeepSeek API（OpenAI 兼容接口）
- 豆包星绘（火山方舟 ARK API）

**前端：**
- 原生 HTML/CSS/JavaScript（无构建工具）
- Marked.js — Markdown 渲染
- ECharts 5 — 数据可视化
- jsPDF + html2canvas — PDF 导出

## 并发与容错

- **并发控制** — 信号量限制最多 3 个 DeepSeek API 并发请求
- **重试机制** — API 调用失败自动重试 3 次，指数退避（1s → 2s → 4s）
- **JSON 容错** — 四级 JSON 解析策略：直接解析 → 提取片段 → 修复常见错误 → 截断补全
- **数据截断** — 输入数据超过 15000 字符自动截断，防止 token 超限

## 常见问题

**Q: 生成失败，提示 500 错误？**
A: 检查 DeepSeek API Key 是否正确，或 API 服务是否可用。查看终端日志获取详细错误信息。

**Q: 没有配图？**
A: 确认 `.env` 中已配置 `ARK_API_KEY`。未配置时配图功能自动降级，显示占位图。

**Q: 图表数据不准确？**
A: 图表数据由 AI 从正文提炼，可通过编辑模式手动修正。点击图表编辑按钮可可视化调整。

**Q: PDF 导出空白？**
A: 确保白皮书已生成完成。导出过程中请勿切换页面。

## License

MIT
