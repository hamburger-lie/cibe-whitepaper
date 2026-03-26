#!/usr/bin/env python3
"""
CIBE 美业数据白皮书自动生成系统 — 后端代理
功能：文件解析、DeepSeek 内容生成、豆包星绘配图生成
"""

import os
import io
import json
import time
import base64
import re
from abc import ABC, abstractmethod
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import pdfplumber
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
import requests
import uvicorn

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5678,http://127.0.0.1:5678").split(",")
]

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------
app = FastAPI(title="CIBE 白皮书生成器")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件：让 index.html 可以直接通过 / 访问
app.mount("/static", StaticFiles(directory="."), name="static")


# ---------------------------------------------------------------------------
# 文件解析引擎
# ---------------------------------------------------------------------------
class FileParser:
    """支持 CSV / Word / PDF 三格式解析"""

    @staticmethod
    def parse(filename: str, content: bytes) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        parsers = {
            "csv": FileParser._parse_csv,
            "xlsx": FileParser._parse_csv,
            "xls": FileParser._parse_csv,
            "docx": FileParser._parse_docx,
            "pdf": FileParser._parse_pdf,
        }
        parser = parsers.get(ext)
        if not parser:
            raise ValueError(f"不支持的文件格式: .{ext}，请上传 CSV / Word / PDF 文件")
        return parser(content, filename)

    @staticmethod
    def _parse_csv(content: bytes, filename: str = "") -> str:
        """CSV/Excel → 结构化摘要"""
        try:
            ext = filename.rsplit(".", 1)[-1].lower() if filename else "csv"
            if ext in ("xlsx", "xls"):
                df = pd.read_excel(io.BytesIO(content))
            else:
                # 尝试多种编码
                for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                    try:
                        df = pd.read_csv(io.BytesIO(content), encoding=enc)
                        break
                    except (UnicodeDecodeError, Exception):
                        continue
                else:
                    df = pd.read_csv(io.BytesIO(content), encoding="utf-8", errors="replace")

            lines = [
                f"【数据文件摘要】",
                f"行数: {len(df)}，列数: {len(df.columns)}",
                f"列名: {', '.join(df.columns.tolist())}",
                "",
                "【列类型与统计】",
            ]
            for col in df.columns:
                dtype = str(df[col].dtype)
                if pd.api.types.is_numeric_dtype(df[col]):
                    desc = df[col].describe()
                    lines.append(
                        f"  {col} ({dtype}): 均值={desc['mean']:.2f}, "
                        f"最小={desc['min']:.2f}, 最大={desc['max']:.2f}, "
                        f"中位数={desc['50%']:.2f}"
                    )
                else:
                    nunique = df[col].nunique()
                    top_vals = df[col].value_counts().head(5).to_dict()
                    lines.append(f"  {col} ({dtype}): {nunique}个唯一值, Top5: {top_vals}")

            lines.append("")
            lines.append("【前5行样本数据】")
            lines.append(df.head(5).to_string(index=False))
            return "\n".join(lines)
        except Exception as e:
            raise ValueError(f"CSV 解析失败: {str(e)}")

    @staticmethod
    def _parse_docx(content: bytes, filename: str = "") -> str:
        """Word → 纯文本"""
        try:
            doc = Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            if not paragraphs:
                raise ValueError("Word 文档内容为空")
            return "\n".join(paragraphs)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Word 解析失败: {str(e)}")

    @staticmethod
    def _parse_pdf(content: bytes, filename: str = "") -> str:
        """PDF → 纯文本"""
        try:
            text_parts = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            if not text_parts:
                raise ValueError("PDF 文档未提取到文字内容")
            return "\n\n".join(text_parts)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"PDF 解析失败: {str(e)}")


# ---------------------------------------------------------------------------
# LLM 抽象层
# ---------------------------------------------------------------------------
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str) -> str:
        ...


class DeepSeekProvider(LLMProvider):
    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置，请检查 .env 文件")
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

    def generate(self, prompt: str, system: str) -> str:
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=8192,
        )
        return response.choices[0].message.content


# 预留：未来可切换其他 Provider
# class GeminiProvider(LLMProvider): ...
# class GPT4oProvider(LLMProvider): ...


def get_llm_provider() -> LLMProvider:
    """工厂方法：当前返回 DeepSeek，未来可按配置切换"""
    return DeepSeekProvider()


# ---------------------------------------------------------------------------
# 豆包星绘 — 配图生成
# ---------------------------------------------------------------------------
class ImageGenerator:
    """
    豆包星绘 — 通过火山方舟 (Volcengine ARK) OpenAI 兼容接口生成图片
    文档: https://www.volcengine.com/docs/82379/1399424
    """

    ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

    def __init__(self):
        self.api_key = ARK_API_KEY

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, width: int = 768, height: int = 512) -> Optional[str]:
        """
        生成图片，返回 base64 编码的图片数据。
        如果未配置 Key 或生成失败，返回 None。
        """
        if not self.available:
            return None

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            body = {
                "model": "doubao-seedream-3-0-t2i-250415",
                "prompt": prompt,
                "size": f"{width}x{height}",
                "response_format": "b64_json",
                "n": 1,
            }

            resp = requests.post(
                self.ENDPOINT,
                headers=headers,
                json=body,
                timeout=90,
            )
            resp.raise_for_status()
            result = resp.json()

            # OpenAI 兼容格式: {"data": [{"b64_json": "..."}]}
            data_list = result.get("data", [])
            if data_list and data_list[0].get("b64_json"):
                return data_list[0]["b64_json"]

            # 也兼容 url 模式
            if data_list and data_list[0].get("url"):
                img_resp = requests.get(data_list[0]["url"], timeout=30)
                return base64.b64encode(img_resp.content).decode("utf-8")

            print(f"[星绘] 返回数据无图片: {json.dumps(result, ensure_ascii=False)[:200]}")
            return None

        except requests.exceptions.HTTPError as e:
            err_body = ""
            try:
                err_body = e.response.text[:300]
            except Exception:
                pass
            print(f"[星绘] HTTP 错误 {e.response.status_code}: {err_body}")
            return None
        except Exception as e:
            print(f"[星绘] 请求异常: {e}")
            return None


image_generator = ImageGenerator()

# ---------------------------------------------------------------------------
# 四角色 Prompt 体系
# ---------------------------------------------------------------------------

# ========================
# 角色一：白皮书战略官
# ========================
AGENT1_SYSTEM = """# Role: CIBE 美业白皮书战略官

你是服务过国际美妆集团的顶级行业战略顾问，曾主导撰写多份在行业内广泛流传的商业洞察白皮书。
你最擅长的能力只有一个：从杂乱的品牌资料中，识别出真正值钱的行业叙事框架。

# Objective:
基于用户提供的原始资料，为一份面向 CIBE 广州美博会专业观众的行业白皮书，
制定一份「有血有肉、可直接执行」的章节大纲，以 JSON 格式输出。

# 绝对红线（违反即重做）:
1. 只能输出合法 JSON，不含 ```json 标记，不含任何废话或解释。
2. 章节数量：不少于 5 章，不超过 8 章。
3. 每章 content_guidelines 必须具体到「本章必须证明的核心命题」+「至少 2 个必须引用的数据锚点或行业案例」。
4. 禁止空洞章节标题（如"总结"、"前言"），每个标题必须直接点出商业价值。"""

AGENT1_USER = """请基于以下原始数据，策划一份 CIBE 美博会行业白皮书的结构化大纲。

<RAW_DATA>
{data}
</RAW_DATA>

输出 JSON Schema：
{{
  "whitepaper_meta": {{
    "title": "白皮书完整标题",
    "subtitle": "副标题，15字以内",
    "global_tone": "语调定义，例如：专业克制、数据驱动、面向决策层"
  }},
  "chapters": [
    {{
      "chapter_id": "01",
      "chapter_title": "章节标题",
      "core_proposition": "本章必须证明的核心命题，一句话",
      "content_guidelines": "详细撰写指令，包含：核心论点、必引数据锚点、典型案例方向",
      "needs_chart": true,
      "chart_intent": "图表意图，例如：2022-2025年中国功效护肤市场规模年增长率趋势",
      "needs_image": true,
      "image_intent": "符合美妆行业的配图"
    }}
  ]
}}

请立即开始解析，仅输出 JSON："""

# ========================
# 角色二：美业深度主笔
# ========================
AGENT2_SYSTEM = """# Role: CIBE 美业深度撰稿人

你是一位在麦肯锡美妆消费品研究组工作过的资深行业分析师，
现任 CIBE 广州美博会智库首席撰稿人。
你的文章从不堆砌数据，而是让数据为商业判断服务。
你只写让读者「读完觉得涨了真本事」的内容。

# 内容质量红线（每条都是硬约束）:
1. 字数下限：本章正文不得低于 900 字，必须是「咨询公司级」的专业长段落。
2. 禁止要点病：严禁通篇使用无序列表代替论述，必须有严密的逻辑过渡与深度的现象剖析。
3. 商业锐度：每章必须包含至少 1 个让行业人「看到直点头」的洞察判断，不能是常识。
4. 禁止开场白和结束语，直接从正文第一句开始。"""

AGENT2_USER = """白皮书标题：《{title}》
语调基调：{tone}
目标读者：美博会参展品牌决策层、渠道商、投资机构

请撰写第 {chapter_id} 章：【{chapter_title}】
核心命题：{core_proposition}
撰写指令：{guidelines}

图表占位：{chart_placeholder_instruction}
配图占位：{image_placeholder_instruction}

请用 ## 开头，直接输出本章正文："""

# ========================
# 角色三：视觉叙事导演
# ========================
AGENT3_SYSTEM = """# Role: 高端美业商业视觉导演

你深度理解「豆包·星绘」文生图模型的底层逻辑，
专注于将美业商业白皮书中的抽象场景意图，
转化为能被模型精准还原的、具备电影质感的真实摄影指令。
你的每一条 Prompt，都像在向一位顶级商业摄影师下达拍摄简报。

# 豆包·星绘 强制约束红线:
1. 绝对写实：禁止「概念图」「插画」「矢量图」「UI界面」「图表」「几何色块」「赛博朋克」。
   画面必须看起来像一张真实拍摄的高端商业摄影作品。
2. 场景具象化：遇到抽象概念必须落地为可拍摄的真实场景：
   - 「市场增长」→ 「高档美容院奢华接待台特写，玫瑰金装饰细节」
   - 「技术创新」→ 「实验室白大褂研究员手持透明精华液瓶，显微镜背景虚化」
   - 「渠道变革」→ 「直播间美妆达人打光下的护肤品陈列，暖光氛围」
3. 必须包含的画质词：真实感，高端商业产品级摄影，浅景深，精准布光，8K 分辨率，电影级色调。
4. 绝对禁止画面出现：文字、字母、数字、图表坐标轴、按钮、任何 UI 元素。
5. 美业专属美学：画面必须传递出「高端、洁净、专业、值得信赖」的品牌质感。"""

AGENT3_USER = """请将以下场景描述转化为豆包星绘能理解的高品质摄影提示词。

画面意图：{image_intent}
所属章节语境：{chapter_title} — {core_proposition}

请直接输出用于 API 调用的纯中文逗号分隔提示词，不超过 120 字，不含任何标点之外的符号："""

# ========================
# 角色四：图表数据官
# ========================
AGENT4_SYSTEM = """# Role: CIBE 白皮书数据可视化官

你是一位同时精通数据分析与 ECharts 图表配置的专家。
你只做一件事：从已完成的白皮书章节正文中，
精准提炼出最具说服力的数据关系，并将其转化为
可直接被 ECharts 渲染的标准图表配置 JSON。

# 绝对红线:
1. 只能输出合法 JSON，不含 ```json 标记，不含任何废话。
2. type 只能从以下选择：bar / line / pie / area / scatter
3. labels 数量：3 ~ 7 个，不得过少或过多。
4. 如有多个数据系列，datasets 数组长度不超过 3 个，防止图表信息过载。
5. 所有数值必须量级合理，与正文语境一致（例如正文说「破千亿」，数值就不能是个位数）。
6. title 字段：12 字以内，直接点明图表核心结论，而非只描述数据维度。"""

AGENT4_USER = """白皮书标题：《{title}》
当前章节：【{chapter_title}】
图表意图：{chart_intent}

章节正文：
<CHAPTER_CONTENT>
{chapter_markdown}
</CHAPTER_CONTENT>

根据上方正文内容，生成一份 ECharts 图表数据配置。
数据必须来源于或高度吻合正文中的论述，不得凭空捏造与正文矛盾的数字。

输出 JSON Schema：
{{
  "type": "bar",
  "title": "图表核心结论标题，12字以内",
  "labels": ["标签1", "标签2", "标签3"],
  "datasets": [
    {{
      "name": "系列名称",
      "values": [100, 200, 150]
    }}
  ]
}}

请立即输出 JSON："""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _parse_llm_json(raw: str) -> dict:
    """从 LLM 输出中健壮地提取 JSON"""
    clean = raw.strip()
    # 去掉 markdown 代码块
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(clean[start:end])
        raise


# ---------------------------------------------------------------------------
# 四阶段生成管线
# ---------------------------------------------------------------------------
def run_four_agent_pipeline(data_text: str) -> str:
    """
    Agent1(战略官) → [Agent2(主笔) + Agent3(视觉导演)] 并发
    → Agent4(图表数据官) 并发 → 三路合并 → 完整 Markdown
    """
    llm = get_llm_provider()

    # ===== 第一批：战略官 生成大纲（串行）=====
    print("[Pipeline] 第一批：战略官生成大纲...")
    outline_raw = llm.generate(
        prompt=AGENT1_USER.format(data=data_text),
        system=AGENT1_SYSTEM,
    )
    outline = _parse_llm_json(outline_raw)
    meta = outline.get("whitepaper_meta", {})
    chapters = outline.get("chapters", [])
    if not chapters:
        raise ValueError("战略官未生成任何章节")

    title = meta.get("title", "CIBE 美业数据洞察白皮书")
    tone = meta.get("global_tone", "专业、数据驱动")
    print(f"[Pipeline] 大纲完成：{title}，共 {len(chapters)} 章")

    # ===== 第二批：主笔 + 视觉导演（并发）=====
    print("[Pipeline] 第二批：主笔 + 视觉导演并发...")
    chapter_texts = {}   # chapter_id → markdown
    image_prompts = {}   # chapter_id → 摄影提示词

    def _write_chapter(ch):
        ch_id = ch["chapter_id"]
        chart_instr = (
            f'在最合适的段落后插入：[CHART_PLACEHOLDER id="{ch_id}"]'
            if ch.get("needs_chart") else "（本章无需图表）"
        )
        image_instr = (
            f'在最合适的段落后插入：[IMAGE_PLACEHOLDER id="{ch_id}"]'
            if ch.get("needs_image") else "（本章无需配图）"
        )
        md = llm.generate(
            prompt=AGENT2_USER.format(
                title=title,
                tone=tone,
                chapter_id=ch_id,
                chapter_title=ch.get("chapter_title", ""),
                core_proposition=ch.get("core_proposition", ""),
                guidelines=ch.get("content_guidelines", ""),
                chart_placeholder_instruction=chart_instr,
                image_placeholder_instruction=image_instr,
            ),
            system=AGENT2_SYSTEM,
        )
        return ("chapter", ch_id, md.strip())

    def _gen_image_prompt(ch):
        ch_id = ch["chapter_id"]
        prompt_text = llm.generate(
            prompt=AGENT3_USER.format(
                image_intent=ch.get("image_intent", ""),
                chapter_title=ch.get("chapter_title", ""),
                core_proposition=ch.get("core_proposition", ""),
            ),
            system=AGENT3_SYSTEM,
        )
        return ("image", ch_id, prompt_text.strip().strip('"').strip("'"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for ch in chapters:
            futures.append(pool.submit(_write_chapter, ch))
            if ch.get("needs_image"):
                futures.append(pool.submit(_gen_image_prompt, ch))

        for fut in as_completed(futures):
            try:
                kind, ch_id, result = fut.result()
                if kind == "chapter":
                    chapter_texts[ch_id] = result
                elif kind == "image":
                    image_prompts[ch_id] = result
            except Exception as e:
                print(f"[Pipeline] 第二批任务失败: {e}")

    print(f"[Pipeline] 第二批完成：{len(chapter_texts)} 章正文，{len(image_prompts)} 个配图词")

    # ===== 第三批：图表数据官（并发）=====
    print("[Pipeline] 第三批：图表数据官并发...")
    chart_data = {}  # chapter_id → chart dict

    def _gen_chart(ch):
        ch_id = ch["chapter_id"]
        ch_md = chapter_texts.get(ch_id, "")
        if not ch_md:
            return ("chart", ch_id, None)
        raw = llm.generate(
            prompt=AGENT4_USER.format(
                title=title,
                chapter_title=ch.get("chapter_title", ""),
                chart_intent=ch.get("chart_intent", ""),
                chapter_markdown=ch_md,
            ),
            system=AGENT4_SYSTEM,
        )
        return ("chart", ch_id, _parse_llm_json(raw))

    with ThreadPoolExecutor(max_workers=6) as pool:
        chart_futures = []
        for ch in chapters:
            if ch.get("needs_chart"):
                chart_futures.append(pool.submit(_gen_chart, ch))

        for fut in as_completed(chart_futures):
            try:
                _, ch_id, cdata = fut.result()
                if cdata:
                    chart_data[ch_id] = cdata
            except Exception as e:
                print(f"[Pipeline] 图表数据官失败: {e}")

    print(f"[Pipeline] 第三批完成：{len(chart_data)} 个图表")

    # ===== 合并阶段 =====
    print("[Pipeline] 合并三路输出...")
    all_chapter_md = []

    for ch in chapters:
        ch_id = ch.get("chapter_id", "")
        md = chapter_texts.get(ch_id, "")

        # 替换 [CHART_PLACEHOLDER id="XX"]
        if ch_id in chart_data:
            cd = chart_data[ch_id]
            chart_type = cd.get("type", "bar")
            chart_title = cd.get("title", "")
            data_obj = {"labels": cd.get("labels", []), "datasets": cd.get("datasets", [])}
            chart_tag = f'<chart type="{chart_type}" title="{chart_title}" data=\'{json.dumps(data_obj, ensure_ascii=False)}\'></chart>'
            md = re.sub(
                r'\[CHART_PLACEHOLDER\s+id="?' + re.escape(ch_id) + r'"?\]',
                chart_tag,
                md,
            )

        # 替换 [IMAGE_PLACEHOLDER id="XX"]
        if ch_id in image_prompts:
            image_tag = f'<image prompt="{image_prompts[ch_id]}"></image>'
            md = re.sub(
                r'\[IMAGE_PLACEHOLDER\s+id="?' + re.escape(ch_id) + r'"?\]',
                image_tag,
                md,
            )

        all_chapter_md.append(md)

    # 拼合
    subtitle = meta.get("subtitle", "")
    header = f"# {title}\n"
    if subtitle:
        header += f"\n> {subtitle}\n"

    full_markdown = header + "\n\n" + "\n\n---\n\n".join(all_chapter_md)
    print(f"[Pipeline] 白皮书生成完毕，总长度 {len(full_markdown)} 字符")
    return full_markdown


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_index():
    """提供前端页面"""
    return FileResponse("index.html")


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "deepseek": bool(DEEPSEEK_API_KEY),
        "image_gen": image_generator.available,
        "timestamp": int(time.time()),
    }


@app.post("/api/generate")
async def generate_whitepaper(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
):
    """
    主接口：四角色管线 — 战略官 → 主笔+视觉导演 → 图表数据官
    """
    # 1. 获取数据
    data_text = ""
    if file and file.filename:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            data_text = FileParser.parse(file.filename, content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif text and text.strip():
        data_text = text.strip()
    else:
        raise HTTPException(status_code=400, detail="请上传文件或输入文字")

    # 2. 截断过长内容
    MAX_CHARS = 15000
    if len(data_text) > MAX_CHARS:
        data_text = data_text[:MAX_CHARS] + "\n\n...(数据已截断，共{}字符)".format(len(data_text))

    # 3. 四角色生成管线
    try:
        markdown = run_four_agent_pipeline(data_text)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {str(e)}")

    return {"status": "success", "markdown": markdown}


@app.post("/api/generate-image")
async def generate_image(
    prompt: str = Form(...),
    width: int = Form(768),
    height: int = Form(512),
):
    """
    配图生成接口：前端解析到 <image> 标签后调用此接口
    返回 base64 图片或占位提示
    """
    if not image_generator.available:
        return {
            "status": "unavailable",
            "message": "豆包星绘未配置，请在 .env 中设置 VOLCENGINE_ACCESS_KEY 和 VOLCENGINE_SECRET_KEY",
            "image_base64": None,
        }

    # Agent3 已生成高质量中文提示词，直接使用
    image_b64 = image_generator.generate(prompt, width=width, height=height)

    if image_b64:
        return {
            "status": "success",
            "image_base64": image_b64,
        }
    else:
        return {
            "status": "error",
            "message": "图片生成失败，请稍后重试",
            "image_base64": None,
        }


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    # Windows 终端编码兼容
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 50)
    print("  CIBE 美业白皮书生成系统 启动中...")
    print(f"  DeepSeek API: {'已配置' if DEEPSEEK_API_KEY else '未配置'}")
    print(f"  豆包星绘:     {'已配置' if image_generator.available else '未配置(配图功能不可用)'}")
    print(f"  访问地址: http://localhost:5678")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=5678)
