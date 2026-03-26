# CIBE 美业数据白皮书自动生成系统

AI 驱动的行业白皮书生成工具，专为 CIBE 广州国际美博会打造。

## 功能

- 📊 **多格式数据上传** — CSV / Excel / Word / PDF / 直接粘贴
- 🤖 **AI 深度分析** — DeepSeek 大模型生成专业行业洞察
- 📈 **智能图表** — ECharts 自动生成可视化图表（柱状/折线/饼图/面积/散点）
- 🎨 **AI 配图** — 豆包星绘自动生成商务插画（可选）
- 📄 **PDF 导出** — 高清 A4 格式白皮书导出

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

**必填：**
- `DEEPSEEK_API_KEY` — DeepSeek API 密钥

**选填（配图功能）：**
- `VOLCENGINE_ACCESS_KEY` — 火山引擎 Access Key
- `VOLCENGINE_SECRET_KEY` — 火山引擎 Secret Key

### 3. 启动服务

```bash
python proxy.py
```

访问 http://localhost:8000 即可使用。

## 架构

```
浏览器 (index.html)
  ↕ HTTP
Python 代理 (proxy.py / FastAPI)
  ├── 文件解析 (pandas / python-docx / pdfplumber)
  ├── DeepSeek API → 白皮书内容生成
  └── 豆包星绘 API → 配图生成（可选）
```

## 文件结构

```
cibe-whitepaper/
├── proxy.py          # 后端代理
├── index.html        # 前端（单文件）
├── .env.example      # 配置模板
├── requirements.txt  # Python 依赖
└── README.md         # 本文件
```
