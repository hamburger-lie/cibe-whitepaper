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
from typing import Optional, List
import threading
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
    # 全局信号量：限制同时最多 3 个 API 并发请求
    _semaphore = threading.Semaphore(3)

    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置，请检查 .env 文件")
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

    def generate(self, prompt: str, system: str, max_retries: int = 3,
                 max_tokens: int = 8192) -> str:
        """带并发控制和重试的 API 调用"""
        with self._semaphore:
            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.7,
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    wait = 2 ** attempt  # 1s, 2s, 4s 指数退避
                    print(f"[DeepSeek] 请求失败(第{attempt+1}次): {e}, {wait}s后重试...")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(wait)


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
                "watermark": False,
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
# 四角色 Prompt 体系（专业报告级）
# ---------------------------------------------------------------------------

# ========================
# 角色一：白皮书战略官
# ========================
AGENT1_SYSTEM = """# Role: 行业白皮书首席架构师

你是一位为 CBNData、艾瑞咨询、KPMG、德勤等机构操盘过数十份行业白皮书的首席架构师。
你的任务是将原始数据设计成一份面向决策层的标准行业白皮书结构化大纲（JSON），后续将据此自动扩写正文。

# 核心方法论

## 1. 洋葱递进
章节必须形成「宏观背景 → 市场全景 → 细分深挖 → 竞争格局 → 模式创新 → 未来展望」的递进纵深。
严禁平行罗列（如"趋势一/趋势二/趋势三"或多个无推进关系的同级分析）。

## 2. 判断句标题
每章标题必须是结论句/判断句，不是话题词。
✗ "功效护肤市场现状"　✓ "功效护肤正在从营销概念走向临床验证"
✗ "渠道分析"　　　　　✓ "线下体验场景正在重新定义专业品牌的转化效率"

## 3. 完整撰稿 brief
每章必须给出：核心问题、导语、2-4 个二级小节、≥2 个数据锚点、≥1 个案例方向、与上章承接、图表意图、结论小结。

## 4. 研究报告体
全文定位为行业研究报告，不是品牌宣传册、公众号长文或 PPT 提纲。标题稳准硬，禁止空泛判断（"未来可期""机遇与挑战并存"）。

# 视觉规则
图表优先于图片（图表是证据，图片仅辅助）。配图仅限真实可拍摄场景（门店/诊疗/产品/案例现场），禁止抽象概念图和纯氛围图。不得每章都强行配大图。

# 红线
1. 禁止平行堆砌章节、禁止缺失执行摘要/研究说明/结论建议等标准模块。
2. 禁止空话套话营销口号，禁止脱离原始数据胡乱发散。
3. 只输出合法 JSON，不含 ```json 标记，不含任何解释文字。章节严格 4~5 章，每章 sub_sections 不超过 3 个，字段值尽量精简。"""

AGENT1_USER = """基于以下原始数据，设计一份标准行业白皮书的结构化大纲 JSON。

<RAW_DATA>
{data}
</RAW_DATA>

输出 JSON Schema：
{{
  "whitepaper_meta": {{
    "title": "白皮书完整标题（结论导向，不超过25字）",
    "subtitle": "副标题，15字以内",
    "global_tone": "如：深度洞察、数据叙事、决策参考级",
    "target_audience": "目标读者，如：品牌方高层、渠道决策层、投资与战略团队"
  }},
  "document_spec": {{
    "document_type": "标准行业白皮书",
    "narrative_logic": "本书的总体递进逻辑概述",
    "required_sections": ["封面页","执行摘要","目录页","研究说明/数据口径","正文章节","结论与行动建议","参考说明/附录"],
    "visual_rule": "图表优先，图片从属，避免画册化",
    "writing_rule": "偏研究报告体，不写成营销长文"
  }},
  "front_matter": {{
    "executive_summary": {{
      "summary_positioning": "执行摘要的定位",
      "key_findings": ["关键发现1","关键发现2","关键发现3","关键发现4"],
      "core_data_points": ["核心数据结论1","核心数据结论2","核心数据结论3"],
      "executive_judgement": "面向决策层的一句话总判断"
    }},
    "research_note": {{
      "research_object": "研究对象",
      "time_scope": "时间范围",
      "data_sources": ["数据来源类型1","数据来源类型2"],
      "sample_scope": "样本/案例口径",
      "method_boundary": "研究边界与推演边界",
      "term_definition": "关键名词定义（如无可留空）"
    }}
  }},
  "chapters": [
    {{
      "chapter_id": "01",
      "chapter_title": "判断句式章节标题",
      "core_proposition": "本章要回答的核心问题",
      "chapter_intro": "本章导语",
      "sub_sections": [
        {{"section_id":"01-1","section_title":"二级小节标题","section_focus":"该小节聚焦的问题"}},
        {{"section_id":"01-2","section_title":"二级小节标题","section_focus":"该小节聚焦的问题"}}
      ],
      "data_anchors": ["数据锚点1","数据锚点2"],
      "case_direction": "案例方向（具体到品牌/品类/模式/场景）",
      "content_guidelines": "撰稿brief：核心论点+关键关系+数据引用+案例嵌入+与上章承接",
      "transition_from_previous": "与上一章的逻辑承接关系",
      "needs_chart": true,
      "chart_intent": "图表意图：具体数据关系描述",
      "visual_type": "chart / case_photo / none",
      "image_intent": "若需要图片则写具体可拍摄场景；否则写none",
      "chapter_summary": "本章结论小结"
    }}
  ],
  "back_matter": {{
    "conclusion_summary": {{
      "final_judgement": "全书总结性判断",
      "industry_implications": ["对行业的启示1","对行业的启示2"]
    }},
    "action_recommendations": {{
      "for_brands": ["给品牌方的建议1","给品牌方的建议2"],
      "for_channels": ["给渠道方的建议1","给渠道方的建议2"],
      "for_investment_or_strategy": ["给投资/战略团队的建议1","给投资/战略团队的建议2"]
    }},
    "risk_and_boundary_notes": ["风险提示1","边界提示2"],
    "references_or_appendix": {{
      "required": true,
      "content_direction": "参考数据来源说明、附录指标口径、补充案例说明等"
    }}
  }}
}}

仅输出 JSON："""

# ========================
# 角色二：美业深度主笔
# ========================
AGENT2_SYSTEM = """# Role: 行业白皮书资深撰稿人

你是一位曾在 CBNData、艾瑞研究院担任首席分析师的行业深度写作者。
你的写作风格对标的是《第一财经》深度商业报道和麦肯锡行业洞察报告——
不是在"介绍信息"，而是在"构建论证"。

# 写作方法论（决定你输出质量的核心规则）：

## 1. 叙事结构：总-分-总，论证驱动
每章以一个引人入胜的现象/数据/判断开篇（hook），
中间展开 2-3 个支撑论点（每个论点自成一个完整论证段落），
段落之间用逻辑过渡句自然衔接（因果、转折、递进，而非机械编号）。

## 2. 数据嵌入法：数据是证据，不是装饰
- 每个数据必须服务于一个论点，不能为了"显得专业"而堆砌
- 数据必须有上下文：对比基准（同比/环比/对标谁）、时间跨度、"so what"解读
- 格式范例：
  ✗ "市场规模达到5000亿元。"（孤立数据，无意义）
  ✓ "中国功效护肤品市场在2024年突破5000亿元大关，较三年前几乎翻番。这一增速远超同期大盘个位数增长，折射出消费者正在从'感性种草'向'理性选择'的根本性转变。"

## 3. 禁止清单式写作（最重要的红线）
- 严禁出现"首先...其次...再次...最后..."的机械排列
- 严禁通篇无序列表/有序列表代替段落论述
- 允许在必要时使用极短列表（3项以内）辅助说明，但列表前后必须有段落论述包裹
- 每章至少 80% 内容必须是完整的叙述段落

## 4. 语言风格：专业而不呆板
- 避免AI感重的词汇：「赋能」「助力」「打造」「引领」「新质生产力」等空洞套话
- 用具体动词替代万能动词：不说"推动增长"，说"拉高客单价至XXX元"
- 允许使用生动的商业比喻和类比，但不过度文学化
- 敢于给出有锐度的判断，不做"正确的废话"

## 5. 篇幅与密度
- 每章正文 1000-1500 字（不含标题和占位符标签）
- 每 200 字至少出现 1 个具体数据点或案例细节
- 禁止开场白（"在当今时代..."）和总结段（"综上所述..."），直接从第一个论点切入

## 6. 标题编号格式（必须严格遵守）
- 一级章节标题格式：## 一、标题内容 / ## 二、标题内容（中文数字编号由系统传入）
- 二级小节标题格式：### 1. 标题内容 / ### 2. 标题内容
- 三级子标题格式：#### （1）标题内容 / #### （2）标题内容
- 各级标题必须单独成行，不与正文混排

## 7. 段落格式
- 正文每一自然段必须是完整书面段落表达
- 严禁使用项目符号（- / * / •）代替主体论述段落
- 允许的例外：极短辅助说明（3项以内）可使用列表，但前后必须有段落论述

## 8. 占位符规范
- 图表占位：在最能支撑核心数据论证的位置插入，格式 `[CHART_PLACEHOLDER]`
- 配图占位：在场景描述或案例论述后插入，格式 `[IMAGE_PLACEHOLDER]`

## 9. 绝对禁止（违反则输出作废）
- 禁止输出任何括号包裹的建议、备注、说明性文字，如：
  ✗ （图表建议：可展示...）
  ✗ （配图建议：...）
  ✗ （注：...）
  ✗ *（建议...）*
- 禁止输出写作自检清单、TODO、编辑批注
- 禁止对图表/配图的内容做文字说明或建议，占位符标签本身就是全部，不需要任何补充文字
- 输出必须是纯粹的、可直接发表的正文，不含任何指导性或元层级的文字"""

AGENT2_USER = """白皮书标题：《{title}》
语调基调：{tone}
目标读者：{target_audience}

请撰写第 {chapter_id} 章：【{chapter_title}】

核心命题：{core_proposition}
本章导语方向：{chapter_intro}
与上一章的承接：{transition}
撰稿 brief：{guidelines}

二级小节结构：
{sub_sections_text}

数据锚点（必须在正文中引用）：
{data_anchors_text}

案例方向：{case_direction}

本章需总结为：{chapter_summary}

图表占位：{chart_placeholder_instruction}
配图占位：{image_placeholder_instruction}

写作检查清单（请在输出前自检，但不要输出清单本身）：
- [ ] 开篇是一个有冲击力的现象/数据/判断，而非"随着...的发展"
- [ ] 没有连续超过3个无序列表项
- [ ] 每个数据都有对比基准和解读
- [ ] 段落之间有逻辑过渡而非机械编号
- [ ] 没有使用「赋能」「助力」「打造」等空洞词汇
- [ ] 字数达到 1000 字以上
- [ ] 没有任何括号建议/备注/说明性文字（如"图表建议：..."、"配图建议：..."、"注：..."）
- [ ] 输出是纯正文，不含任何元层级评论
- [ ] 二级小节按照给定结构展开，使用 ### 1. / ### 2. 格式
- [ ] 章节末尾有简短结论，自然引出下一章

输出格式要求：
- 第一行必须是：## {chapter_number}、{chapter_title}
- 二级小节按给定结构展开，标题格式：### 1. 小节标题 / ### 2. 小节标题
- 三级子标题格式：#### （1）子标题
- 章节末尾用一小段结论收束（不超过3句，不用"综上所述"开头）
- 只输出正文，不要输出自检清单或任何元注释

请立即输出："""

# ========================
# 角色三：视觉叙事导演
# ========================
AGENT3_SYSTEM = """# Role: 高端商业视觉导演

你深度理解「豆包·星绘」文生图模型的底层逻辑，
专注于将商业白皮书中的抽象场景意图，
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
5. 画面必须传递出「高端、洁净、专业、值得信赖」的品牌质感。"""

AGENT3_USER = """请将以下场景描述转化为豆包星绘能理解的高品质摄影提示词。

画面意图：{image_intent}
所属章节语境：{chapter_title} — {core_proposition}

请直接输出用于 API 调用的纯中文逗号分隔提示词，不超过 120 字，不含任何标点之外的符号："""

# ========================
# 角色四：图表数据官
# ========================
AGENT4_SYSTEM = """# Role: 数据可视化官

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
    """从 LLM 输出中健壮地提取 JSON，自动修复常见问题"""
    clean = raw.strip()
    # 去掉 markdown 代码块
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    # 第一次尝试：直接解析
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # 第二次尝试：提取最外层 { ... }
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start >= 0 and end > start:
        fragment = clean[start:end]
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            pass

        # 第三次尝试：修复常见 LLM JSON 错误
        fixed = fragment
        # 修复尾部多余逗号 (trailing comma before } or ])
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        # 修复中文引号
        fixed = fixed.replace('\u201c', '"').replace('\u201d', '"')
        fixed = fixed.replace('\u2018', "'").replace('\u2019', "'")
        # 修复未转义的换行符在字符串值内
        fixed = re.sub(r'(?<=": ")(.*?)(?=")', lambda m: m.group(0).replace('\n', '\\n'), fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # 第四次尝试：修复被截断的 JSON（补全缺失的括号）
    candidate = clean[start:] if start >= 0 else clean
    # 扫描：跟踪字符串状态和括号栈
    in_str = False
    last_safe = 0  # 最后一个结构完整的位置
    stack = []     # 记录 { [ 的嵌套顺序
    i = 0
    while i < len(candidate):
        ch = candidate[i]
        if ch == '\\' and in_str:
            i += 2
            continue
        if ch == '"':
            in_str = not in_str
            if not in_str:
                last_safe = i + 1
        elif not in_str:
            if ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
                last_safe = i + 1
            elif ch in ('}', ']'):
                if stack:
                    stack.pop()
                last_safe = i + 1
            else:
                # 数字、布尔值、逗号、冒号等也是安全位置
                last_safe = i + 1
        i += 1
    if in_str or stack:
        # 回退到最后安全位置，然后补全
        candidate = candidate[:last_safe]
        candidate = re.sub(r',\s*$', '', candidate)
        candidate = re.sub(r',\s*"[^"]*"\s*:\s*$', '', candidate)
        # 重新计算剩余未闭合括号
        stack2 = []
        in_str2 = False
        for ch in candidate:
            if ch == '"' and (not candidate or True):
                in_str2 = not in_str2
            elif not in_str2:
                if ch in ('{', '['):
                    stack2.append('}' if ch == '{' else ']')
                elif ch in ('}', ']') and stack2:
                    stack2.pop()
        # 按嵌套逆序补全
        candidate += ''.join(reversed(stack2))
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 全部失败，抛出有用的错误信息
    preview = clean[:200] + '...' if len(clean) > 200 else clean
    raise ValueError(f"无法解析 LLM 返回的 JSON。前200字符: {preview}")


# ---------------------------------------------------------------------------
# 四阶段生成管线
# ---------------------------------------------------------------------------
def run_four_agent_pipeline(data_text: str) -> str:
    """
    Agent1(战略官) → [Agent2(主笔) + Agent3(视觉导演)] 并发
    → Agent4(图表数据官) 并发 → 合并完整白皮书 Markdown
    新版：支持 front_matter / back_matter / sub_sections 等完整白皮书体例
    """
    llm = get_llm_provider()

    # ===== 第一批：战略官 生成大纲（串行，带重试）=====
    print("[Pipeline] 第一批：战略官生成大纲...")
    outline = None
    for attempt in range(3):
        try:
            outline_raw = llm.generate(
                prompt=AGENT1_USER.format(data=data_text),
                system=AGENT1_SYSTEM,
            )
            outline = _parse_llm_json(outline_raw)
            break
        except Exception as e:
            print(f"[Pipeline] 战略官第 {attempt+1} 次尝试失败: {e}")
            if attempt == 2:
                raise ValueError(f"战略官连续 3 次生成大纲失败: {e}")
    meta = outline.get("whitepaper_meta", {})
    front_matter = outline.get("front_matter", {})
    back_matter = outline.get("back_matter", {})
    chapters = outline.get("chapters", [])
    if not chapters:
        raise ValueError("战略官未生成任何章节")

    title = meta.get("title", "CIBE 美业数据洞察白皮书")
    subtitle = meta.get("subtitle", "")
    tone = meta.get("global_tone", "专业、数据驱动")
    target_audience = meta.get("target_audience", "行业决策层、渠道商、投资机构")
    print(f"[Pipeline] 大纲完成：{title}，共 {len(chapters)} 章")

    # ===== 第二批：主笔 + 视觉导演（并发）=====
    print("[Pipeline] 第二批：主笔 + 视觉导演并发...")
    chapter_texts = {}   # chapter_id → markdown
    image_prompts = {}   # chapter_id → 摄影提示词

    def _write_chapter(ch, ch_idx):
        CN_NUMS = "一二三四五六七八九十"
        ch_number = CN_NUMS[ch_idx - 1] if ch_idx <= 10 else str(ch_idx)
        ch_id = ch["chapter_id"]
        chart_instr = (
            f'在最合适的段落后插入：[CHART_PLACEHOLDER id="{ch_id}"]'
            if ch.get("needs_chart") else "（本章无需图表）"
        )
        # image_intent 不为 none 就需要配图
        img_intent = ch.get("image_intent", "none")
        needs_img = bool(img_intent and img_intent.strip().lower() != "none")
        image_instr = (
            f'在最合适的案例/场景段落后插入：[IMAGE_PLACEHOLDER id="{ch_id}"]'
            if needs_img else "（本章无需配图）"
        )
        # 构造二级小节文本
        sub_sections = ch.get("sub_sections", [])
        sub_text = "\n".join(
            f"- {s.get('section_id','')}: {s.get('section_title','')} — {s.get('section_focus','')}"
            for s in sub_sections
        ) if sub_sections else "（由你自行组织二级结构）"
        # 构造数据锚点文本
        anchors = ch.get("data_anchors", [])
        anchors_text = "\n".join(f"- {a}" for a in anchors) if anchors else "（从正文内容中自行提取关键数据）"

        md = llm.generate(
            prompt=AGENT2_USER.format(
                title=title,
                tone=tone,
                target_audience=target_audience,
                chapter_id=ch_id,
                chapter_title=ch.get("chapter_title", ""),
                core_proposition=ch.get("core_proposition", ""),
                chapter_intro=ch.get("chapter_intro", ""),
                transition=ch.get("transition_from_previous", ""),
                guidelines=ch.get("content_guidelines", ""),
                sub_sections_text=sub_text,
                data_anchors_text=anchors_text,
                case_direction=ch.get("case_direction", ""),
                chapter_summary=ch.get("chapter_summary", ""),
                chart_placeholder_instruction=chart_instr,
                image_placeholder_instruction=image_instr,
                chapter_number=ch_number,
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

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = []
        for ch_idx, ch in enumerate(chapters, 1):
            futures.append(pool.submit(_write_chapter, ch, ch_idx))
            # image_intent 不为 none 就生成配图（不受 visual_type 限制）
            img_intent = ch.get("image_intent", "none")
            if img_intent and img_intent.strip().lower() != "none":
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

    with ThreadPoolExecutor(max_workers=3) as pool:
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
    print("[Pipeline] 合并完整白皮书...")

    # 清理正文中残留的括号建议/元注释
    _meta_comment_re = re.compile(
        r'[（(]\s*(?:图表建议|配图建议|建议|注|备注|说明|编辑批注|TODO)\s*[：:].+?[）)]\s*',
        re.DOTALL,
    )
    _star_comment_re = re.compile(
        r'\*\s*[（(]\s*(?:图表建议|配图建议|建议|注).+?[）)]\s*\*\s*',
        re.DOTALL,
    )

    # --- 封面 ---
    parts = []
    header = f"# {title}\n"
    if subtitle:
        header += f"\n> {subtitle}\n"
    parts.append(header)

    # --- 执行摘要 ---
    exec_summary = front_matter.get("executive_summary", {})
    if exec_summary:
        es_lines = ["## 执行摘要\n"]
        # 总判断
        judgement = exec_summary.get("executive_judgement", "")
        if judgement:
            es_lines.append(f"**核心判断：** {judgement}\n")
        # 关键发现
        findings = exec_summary.get("key_findings", [])
        if findings:
            es_lines.append("### 关键发现\n")
            for i, f in enumerate(findings, 1):
                es_lines.append(f"**{i}.** {f}\n")
        # 核心数据结论
        data_pts = exec_summary.get("core_data_points", [])
        if data_pts:
            es_lines.append("### 核心数据\n")
            for d in data_pts:
                es_lines.append(f"- {d}")
        parts.append("\n".join(es_lines))

    # --- 目录 ---
    toc_lines = ["## 目录\n"]
    toc_lines.append("- 执行摘要")
    toc_lines.append("- 研究说明")
    for i, ch in enumerate(chapters, 1):
        ch_title = ch.get("chapter_title", f"第{i}章")
        toc_lines.append(f"{i}. {ch_title}")
        for s in ch.get("sub_sections", []):
            toc_lines.append(f"   - {s.get('section_title', '')}")
    toc_lines.append("- 结论与行动建议")
    toc_lines.append("- 参考说明")
    parts.append("\n".join(toc_lines))

    # --- 研究说明 ---
    research = front_matter.get("research_note", {})
    if research:
        rn_lines = ["## 研究说明\n"]
        if research.get("research_object"):
            rn_lines.append(f"**研究对象：** {research['research_object']}\n")
        if research.get("time_scope"):
            rn_lines.append(f"**时间范围：** {research['time_scope']}\n")
        sources = research.get("data_sources", [])
        if sources:
            rn_lines.append(f"**数据来源：** {'、'.join(sources)}\n")
        if research.get("sample_scope"):
            rn_lines.append(f"**样本口径：** {research['sample_scope']}\n")
        if research.get("method_boundary"):
            rn_lines.append(f"**研究边界：** {research['method_boundary']}\n")
        if research.get("term_definition"):
            rn_lines.append(f"**名词定义：** {research['term_definition']}\n")
        parts.append("\n".join(rn_lines))

    # --- 正文章节 ---
    for ch in chapters:
        ch_id = ch.get("chapter_id", "")
        md = chapter_texts.get(ch_id, "")
        # 清理元注释
        md = _meta_comment_re.sub('', md)
        md = _star_comment_re.sub('', md)

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

        parts.append(md)

    # --- 结论与行动建议 ---
    if back_matter:
        conclusion = back_matter.get("conclusion_summary", {})
        actions = back_matter.get("action_recommendations", {})
        risks = back_matter.get("risk_and_boundary_notes", [])

        bm_lines = ["## 结论与行动建议\n"]
        if conclusion.get("final_judgement"):
            bm_lines.append(f"**总结性判断：** {conclusion['final_judgement']}\n")
        implications = conclusion.get("industry_implications", [])
        if implications:
            bm_lines.append("### 行业启示\n")
            for imp in implications:
                bm_lines.append(f"- {imp}")
            bm_lines.append("")

        if actions:
            if actions.get("for_brands"):
                bm_lines.append("### 对品牌方的建议\n")
                for a in actions["for_brands"]:
                    bm_lines.append(f"- {a}")
                bm_lines.append("")
            if actions.get("for_channels"):
                bm_lines.append("### 对渠道方的建议\n")
                for a in actions["for_channels"]:
                    bm_lines.append(f"- {a}")
                bm_lines.append("")
            if actions.get("for_investment_or_strategy"):
                bm_lines.append("### 对投资/战略团队的建议\n")
                for a in actions["for_investment_or_strategy"]:
                    bm_lines.append(f"- {a}")
                bm_lines.append("")

        if risks:
            bm_lines.append("### 风险与边界提示\n")
            for r in risks:
                bm_lines.append(f"- {r}")
            bm_lines.append("")

        parts.append("\n".join(bm_lines))

    # --- 参考说明 ---
    refs = back_matter.get("references_or_appendix", {})
    if refs and refs.get("required"):
        ref_lines = ["## 参考说明与附录\n"]
        if refs.get("content_direction"):
            ref_lines.append(f"{refs['content_direction']}\n")
        parts.append("\n".join(ref_lines))

    # --- 拼合 ---
    full_markdown = "\n\n---\n\n".join(parts)
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
    files: List[UploadFile] = File([]),
    text: Optional[str] = Form(None),
):
    """
    主接口：四角色管线 — 战略官 → 主笔+视觉导演 → 图表数据官
    支持同时上传多个文件 + 可选文字输入
    """
    # 1. 获取数据（多文件 + 文字拼合）
    data_parts = []
    for f in files:
        if not f.filename:
            continue
        content = await f.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"文件 {f.filename} 为空")
        try:
            parsed = FileParser.parse(f.filename, content)
            data_parts.append(f"【文件: {f.filename}】\n{parsed}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if text and text.strip():
        data_parts.append(f"【文字输入】\n{text.strip()}")
    if not data_parts:
        raise HTTPException(status_code=400, detail="请上传文件或输入文字")
    data_text = "\n\n---\n\n".join(data_parts)

    # 2. 截断过长内容
    MAX_CHARS = 15000
    if len(data_text) > MAX_CHARS:
        data_text = data_text[:MAX_CHARS] + "\n\n...(数据已截断，共{}字符)".format(len(data_text))

    # 3. 四角色生成管线
    try:
        markdown = run_four_agent_pipeline(data_text)
    except (RuntimeError, ValueError) as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
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
