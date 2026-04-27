# CIBE 美业数据白皮书自动生成系统

AI 驱动的行业白皮书自动生成工具，专为 CIBE 广州国际美博会打造。融合文件解析、大模型内容生成、智能数据可视化、AI 配图、反思增强与联网数据核查等能力，支持多格式输入，自动生成专业级行业白皮书。

## 功能特性

- **多格式数据输入** — 支持 CSV / Excel / Word / PDF 文件上传，也支持直接粘贴文本
- **四角色 AI 管线** — 战略官设计大纲 → 主笔撰写正文 + 视觉导演生成配图 → 图表数据官生成可视化
- **智能图表** — ECharts 自动生成可视化图表（柱状图 / 折线图 / 饼图 / 面积图 / 散点图）
- **AI 配图** — 豆包星绘生成高端商业摄影风格配图（可选）
- **反思增强**（可选） — 白皮书生成后由反思代理按既定评估准则复检，低分章节自动重写
- **联网数据核查**（可选） — 通过 Scrapfly 云爬虫代理对正文关键数据进行联网核实
- **上传数据验证**（可选） — 对上传文件做质量评分，产出可读性建议
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
│                  │  合并 → 白皮书 Markdown          │   │
│                  │       ↓                        │   │
│                  │  反思代理复检(可选)→ 低分重写    │   │
│                  │       ↓                        │   │
│                  │  联网核查(可选) → 数据校准      │   │
│                  └───────────────────────────────┘   │
│                                                      │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────┐ │
│  │ DeepSeek API │  │ 豆包星绘 API    │  │ Scrapfly  │ │
│  │ (文本生成)    │  │ (配图,可选)     │  │ (可选)  │ │
│  └──────────────┘  └────────────────┘  └─────────┘ │
└──────────────────────────────────────────────────────┘
```

### 四角色分工

| 角色 | 职责 | 输出 |
|------|------|------|
| **Agent1 战略官** | 将原始数据设计为白皮书结构化大纲 | JSON 大纲（含章节、数据锚点、图表意图等） |
| **Agent2 主笔** | 撰写各章正文，总-分-总论证结构 | Markdown 正文（1000-1500 字/章） |
| **Agent3 视觉导演** | 将章节场景转化为摄影指令 | 豆包星绘 Prompt |
| **Agent4 图表数据官** | 从正文提炼数据，生成图表配置 | ECharts JSON 配置 |

### 反思与校验层（扩展能力）

| 模块 | 职责 |
|------|------|
| `reflection_criteria.py` | 白皮书质量评估准则（章节完整度、数据密度、可读性等） |
| `reflection_agent.py` | 按准则复检已生成的白皮书，识别薄弱章节 |
| `reflection_storage.py` | 反思记录持久化到 `reflections.json` |
| `web_search.py` | 基于 Scrapfly API 的联网搜索封装，支持关键词/事实核查 |
| `data_verification.py` | 上传数据的质量评分与改进建议 |

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
- `fastapi` / `uvicorn` — Web 框架与 ASGI 服务器
- `openai` — DeepSeek API 客户端（OpenAI 兼容）
- `pandas` — CSV/Excel 数据处理
- `python-docx` — Word 文件解析
- `pdfplumber` — PDF 文本提取
- `requests` — HTTP 请求
- `python-multipart` — 文件上传支持
- `python-dotenv` — 环境变量管理
- `requests` — 联网搜索与 Scrapfly 云爬虫 HTTP 调用

### 3. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入真实密钥。完整变量清单见下表：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek 文本生成密钥，获取: https://platform.deepseek.com/ |
| `ARK_API_KEY` | 否 | 豆包星绘配图密钥，未配置则配图功能降级为占位图。获取: https://www.volcengine.com/product/doubao |
| `SCRAPFLY_API_KEY` | 否 | Scrapfly 云爬虫密钥，未配置则回退本机直连，可能被搜索引擎反爬拦截。获取: https://scrapfly.io/ |
| `RESEARCH_BUDGET_MODE` | 否 | 联网研究预算模式：`economy` / `balanced` / `deep` / `legacy`，默认 `balanced`。 |
| `RESEARCH_MAX_SEARCH_REQUESTS` | 否 | 单次白皮书最多搜索请求数，默认 `30`。 |
| `RESEARCH_MAX_FETCH_PAGES` | 否 | 单次白皮书最多抓取候选页面数，默认 `40`。 |
| `RESEARCH_TARGET_REFERENCES` | 否 | 最终交给 AI 使用的目标参考资料数，默认 `10`。 |
| `SCRAPFLY_COST_BUDGET_SEARCH` | 否 | Scrapfly 单个搜索页请求成本上限，默认 `3` credits。 |
| `SCRAPFLY_COST_BUDGET_PAGE` | 否 | Scrapfly 单个文章页请求成本上限，默认 `5` credits。 |
| `SCRAPFLY_CACHE_TTL` | 否 | Scrapfly 缓存复用时间，默认 `604800` 秒，即 7 天。 |
| `ALLOWED_ORIGINS` | 否 | CORS 白名单，逗号分隔。默认 `http://localhost:5678,http://127.0.0.1:5678` |
| `ENABLE_REFLECTION` | 否 | 反思增强开关，默认 `true` |
| `ENABLE_WEB_SEARCH` | 否 | 联网搜索开关，默认 `true` |
| `ENABLE_DATA_VERIFICATION` | 否 | 旧版逐数字联网核查开关，默认 `false`，避免生成后再触发大量人工审核噪声。 |
| `REFLECTION_STORAGE_PATH` | 否 | 反思记录存储路径，默认 `reflections.json` |
| `WEB_SEARCH_TIMEOUT` | 否 | 联网搜索超时（秒），默认 `10` |

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
3. 若启用反思功能，系统会自动评估白皮书质量并对低分章节重写
4. 若启用联网核查，关键数据会进行 Scrapfly 搜索比对
5. 生成完成后，白皮书自动渲染在预览区

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

### 核心接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/health` | GET | 健康检查，返回各 API / 扩展功能开关状态 |
| `/api/generate` | POST | 白皮书生成（上传文件 + 文本） |
| `/api/generate-image` | POST | AI 配图生成 |

### 扩展接口（反思 / 核查）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/verify-data` | POST | 对上传文件做质量评分与改进建议 |
| `/api/reflect-report` | POST | 创建反思报告 |
| `/api/reflect-report/{report_id}` | GET | 获取指定反思报告详情 |
| `/api/reflect-report/{report_id}` | DELETE | 删除指定反思报告 |
| `/api/reflection-history` | GET | 分页查询反思历史（支持 `limit`/`offset`/`reflection_type`） |

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

### POST /api/verify-data

**请求：** `multipart/form-data`
- `files` — 待验证文件（支持多个）
- `text` — 文本输入（可选）

**响应：** 每个文件返回 `status / message / details`，含数据行数、列数、缺失率等质量指标。

### POST /api/reflect-report

**请求：** `multipart/form-data`
- `report_id` — 报告唯一 ID（必填）
- `content` — 反思正文（必填）
- `reflection_type` — 类型标签，默认 `general`
- `source_data` — 关联的原始数据（可选）
- `analysis_metadata` — JSON 字符串，附加元数据（可选）

**响应：** 创建成功返回 `reflection_id` / `timestamp` / `metadata`。

### GET /api/reflection-history

**查询参数：**
- `limit` — 返回条数，1–200，默认 50
- `offset` — 偏移量，默认 0
- `reflection_type` — 按类型筛选（可选）

**响应：** 含 `reflections` 列表与 `pagination` 分页信息。

## 文件结构

```
cibe-whitepaper/
├── proxy.py                     # 后端服务（FastAPI + 四角色 AI 管线 + 反思 / 核查路由）
├── index.html                   # 前端界面（单文件，含 CSS/JS）
├── enhanced_styles.css          # 前端附加样式
├── reflection_agent.py          # 反思代理（按评估准则复检白皮书）
├── reflection_criteria.py       # 反思评估准则定义
├── reflection_storage.py        # 反思记录持久化
├── web_search.py                # Scrapfly 联网搜索封装
├── data_verification.py         # 上传数据质量评分
├── test_basic.py                # 基础功能测试
├── test_integration.py          # 集成测试
├── test_reflection.py           # 反思功能测试
├── test_reflection_agent.py     # 反思代理测试
├── test_web_search.py           # 联网搜索测试
├── test_enhanced_features.py    # 扩展功能端到端测试
├── web_search_examples.py       # 联网搜索使用示例
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
├── .env                         # 环境变量（自行创建，不纳入版本控制）
├── .gitignore                   # Git 忽略规则
└── README.md                    # 项目文档
```

> 启动入口统一为 `python proxy.py`。

## 技术栈

**后端：**
- Python 3.9+ / FastAPI / Uvicorn
- DeepSeek API（OpenAI 兼容接口）
- 豆包星绘（火山方舟 ARK API）
- Scrapfly（联网搜索，反思 / 核查用）

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
- **反思兜底** — 反思代理对每章按既定准则评分，低于阈值的章节自动重写一次
- **联网降级** — 未配置 `SCRAPFLY_API_KEY` 时回退本机直连，不影响白皮书主流程

## 常见问题

**Q: 生成失败，提示 500 错误？**
A: 检查 DeepSeek API Key 是否正确，或 API 服务是否可用。查看终端日志获取详细错误信息。

**Q: 没有配图？**
A: 确认 `.env` 中已配置 `ARK_API_KEY`。未配置时配图功能自动降级，显示占位图。

**Q: 联网核查没生效？**
A: 确认已配置 `SCRAPFLY_API_KEY` 且 `ENABLE_WEB_SEARCH=true`。超时可通过 `WEB_SEARCH_TIMEOUT` 调整。

**Q: 图表数据不准确？**
A: 图表数据由 AI 从正文提炼，可通过编辑模式手动修正。点击图表编辑按钮可可视化调整。

**Q: PDF 导出空白？**
A: 确保白皮书已生成完成。导出过程中请勿切换页面。

**Q: 如何关闭反思 / 联网功能？**
A: 在 `.env` 中将 `ENABLE_REFLECTION` / `ENABLE_WEB_SEARCH` / `ENABLE_DATA_VERIFICATION` 设为 `false` 即可。

## License

MIT

