#!/usr/bin/env python3
"""
Lightweight web research bridge for report generation.

This module prioritizes recent official, institutional, and authoritative media
sources, then prepares a compact research brief for the whitepaper pipeline.
"""

from __future__ import annotations

import os
import re
import base64
import json
import hashlib
import time
import threading
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urljoin, urlparse

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()

# ---------------------------------------------------------------------------
# Scrapfly 云爬虫 API（serverless anti-bot proxy）
# 配置后搜索引擎查询和页面抓取会通过 Scrapfly 转发，绕过本机 IP 反爬。
# 文档：https://scrapfly.io/docs/scrape-api/getting-started
# ---------------------------------------------------------------------------
SCRAPFLY_API_KEY: str = os.getenv("SCRAPFLY_API_KEY", "").strip()
SCRAPFLY_ENDPOINT = "https://api.scrapfly.io/scrape"


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _safe_int(value: Any, default: Optional[int] = 0) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


RESEARCH_BUDGET_MODE = os.getenv("RESEARCH_BUDGET_MODE", "balanced").strip().lower() or "balanced"
_BUDGET_PRESETS = {
    "economy": {"search": 12, "fetch": 16, "target": 8},
    "balanced": {"search": 32, "fetch": 48, "target": 10},
    "deep": {"search": 64, "fetch": 64, "target": 12},
    "legacy": {"search": 96, "fetch": 80, "target": 10},
}
_BUDGET_DEFAULTS = _BUDGET_PRESETS.get(RESEARCH_BUDGET_MODE, _BUDGET_PRESETS["balanced"])
RESEARCH_MAX_SEARCH_REQUESTS = _int_env("RESEARCH_MAX_SEARCH_REQUESTS", _BUDGET_DEFAULTS["search"])
RESEARCH_MAX_FETCH_PAGES = _int_env("RESEARCH_MAX_FETCH_PAGES", _BUDGET_DEFAULTS["fetch"])
RESEARCH_TARGET_REFERENCES = _int_env("RESEARCH_TARGET_REFERENCES", _BUDGET_DEFAULTS["target"])
SCRAPFLY_COST_BUDGET_SEARCH = _int_env("SCRAPFLY_COST_BUDGET_SEARCH", 3)
SCRAPFLY_COST_BUDGET_PAGE = _int_env("SCRAPFLY_COST_BUDGET_PAGE", 5)
SCRAPFLY_CACHE_TTL = _int_env("SCRAPFLY_CACHE_TTL", 604800, minimum=0)
RESEARCH_MEMORY_PATH = os.getenv("RESEARCH_MEMORY_PATH", os.path.join("data", "research_memory.json"))
RESEARCH_CACHE_PATH = os.getenv("RESEARCH_CACHE_PATH", os.path.join("data", "research_cache.json"))
RESEARCH_CACHE_TTL = _int_env("RESEARCH_CACHE_TTL", 86400, minimum=0)
RESEARCH_FETCH_BATCH_SIZE = _int_env("RESEARCH_FETCH_BATCH_SIZE", 8, minimum=1)
RESEARCH_SEARCH_WORKERS = _int_env("RESEARCH_SEARCH_WORKERS", 3, minimum=1)
SCRAPFLY_SEARCH_CONCURRENCY = _int_env("SCRAPFLY_SEARCH_CONCURRENCY", 2, minimum=1)
SCRAPFLY_SEARCH_RETRIES = _int_env("SCRAPFLY_SEARCH_RETRIES", 3, minimum=1)
SCRAPFLY_SEARCH_BACKOFF_SECONDS = _int_env("SCRAPFLY_SEARCH_BACKOFF_SECONDS", 2, minimum=1)
RESEARCH_EARLY_STOP_MIN_RESULTS = _int_env("RESEARCH_EARLY_STOP_MIN_RESULTS", 10, minimum=1)
RESEARCH_EARLY_STOP_MIN_SCORE = _int_env("RESEARCH_EARLY_STOP_MIN_SCORE", 60, minimum=1)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
RESEARCH_AI_RERANK_ENABLED = os.getenv("RESEARCH_AI_RERANK_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
RESEARCH_AI_RERANK_CANDIDATES = _int_env("RESEARCH_AI_RERANK_CANDIDATES", 24, minimum=1)
_SCRAPFLY_SEARCH_SEMAPHORE = threading.BoundedSemaphore(SCRAPFLY_SEARCH_CONCURRENCY)
MEMORY_ALWAYS_BLOCK_DOMAINS = (
    "music.163.com",
    "y.qq.com",
    "kuwo.cn",
    "kugou.com",
)


def _record_research_failure(reason: str, topic: str, bad_sources: List[str]) -> None:
    try:
        os.makedirs(os.path.dirname(RESEARCH_MEMORY_PATH) or ".", exist_ok=True)
        records = []
        if os.path.exists(RESEARCH_MEMORY_PATH):
            with open(RESEARCH_MEMORY_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    records = loaded
        records.append(
            {
                "timestamp": int(datetime.now().timestamp()),
                "reason": reason,
                "topic": topic,
                "bad_sources": list(dict.fromkeys(bad_sources))[:12],
                "lesson": "低质量来源不要进入候选或最终参考；优先品牌+产品双命中、机构报告、行业媒体和可读正文。",
            }
        )
        with open(RESEARCH_MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(records[-50:], f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[Research][Memory] 记录失败记忆失败: {exc}")


def _load_research_lessons(topic: str = "", limit: int = 5) -> str:
    try:
        if not os.path.exists(RESEARCH_MEMORY_PATH):
            return ""
        with open(RESEARCH_MEMORY_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            return ""
        required_terms = set(extract_required_topic_terms(topic)) if topic else set()
        matched = []
        for record in reversed(records):
            record_terms = set(extract_required_topic_terms(record.get("topic", "")))
            if not required_terms or required_terms & record_terms:
                matched.append(record)
            if len(matched) >= limit:
                break
        if not matched:
            return ""
        lines = ["研究失败记忆："]
        for item in matched:
            sources = "、".join(item.get("bad_sources") or [])
            lines.append(
                f"- 主题 {item.get('topic', '')} 曾因 {item.get('reason', '')} 选源太差；低质量来源: {sources}；修正: {item.get('lesson', '')}"
            )
        return "\n".join(lines)
    except Exception as exc:
        print(f"[Research][Memory] 读取失败记忆失败: {exc}")
        return ""


def _load_research_bad_sources(topic: str = "", limit: int = 8) -> List[str]:
    try:
        if not os.path.exists(RESEARCH_MEMORY_PATH):
            return []
        with open(RESEARCH_MEMORY_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            return []
        required_terms = set(extract_required_topic_terms(topic)) if topic else set()
        bad_sources: List[str] = []
        for record in reversed(records):
            if record.get("reason") not in {"entertainment_content", "low_quality_source"}:
                continue
            record_terms = set(extract_required_topic_terms(record.get("topic", "")))
            if required_terms and not (required_terms & record_terms):
                continue
            for source in record.get("bad_sources") or []:
                normalized = str(source or "").strip().lower()
                if is_preferred_publisher(normalized) and not any(
                    domain_matches(normalized, blocked) for blocked in MEMORY_ALWAYS_BLOCK_DOMAINS
                ):
                    continue
                if normalized and normalized not in bad_sources:
                    bad_sources.append(normalized)
            if len(bad_sources) >= limit:
                break
        return bad_sources[:limit]
    except Exception as exc:
        print(f"[Research][Memory] 读取坏源失败: {exc}")
        return []


def _research_cache_key(topic: str) -> str:
    normalized = re.sub(r"\s+", " ", (topic or "").strip().lower())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _load_research_cache(topic: str) -> Optional[Dict[str, Any]]:
    try:
        if RESEARCH_CACHE_TTL <= 0 or not os.path.exists(RESEARCH_CACHE_PATH):
            return None
        with open(RESEARCH_CACHE_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, dict):
            return None
        cached = records.get(_research_cache_key(topic))
        if not isinstance(cached, dict):
            return None
        timestamp = int(cached.get("timestamp", 0) or 0)
        if int(datetime.now().timestamp()) - timestamp > RESEARCH_CACHE_TTL:
            return None
        payload = cached.get("payload")
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        print(f"[Research][Cache] 读取缓存失败: {exc}")
        return None


def _save_research_cache(topic: str, payload: Dict[str, Any]) -> None:
    try:
        if RESEARCH_CACHE_TTL <= 0:
            return
        os.makedirs(os.path.dirname(RESEARCH_CACHE_PATH) or ".", exist_ok=True)
        records: Dict[str, Any] = {}
        if os.path.exists(RESEARCH_CACHE_PATH):
            with open(RESEARCH_CACHE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    records = loaded
        records[_research_cache_key(topic)] = {
            "timestamp": int(datetime.now().timestamp()),
            "topic": topic,
            "payload": payload,
        }
        trimmed = dict(list(records.items())[-100:])
        with open(RESEARCH_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"[Research][Cache] 写入缓存失败: {exc}")


class _ScrapflyResponse:
    """伪装成 requests.Response 的最小接口，供现有解析器消费。"""

    def __init__(
        self,
        status_code: int,
        text: str,
        url: str,
        headers: dict,
        cost: int = 0,
        remaining_credit: Optional[int] = None,
        cache_state: str = "",
    ):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8", errors="ignore")
        self.url = url
        self.headers = headers or {}
        self.cost = cost
        self.remaining_credit = remaining_credit
        self.cache_state = cache_state

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"Scrapfly returned {self.status_code}")


def _scrapfly_fetch(
    target_url: str,
    params: Optional[dict] = None,
    timeout: int = 30,
    render_js: bool = False,
    country: str = "cn",
    cost_budget: Optional[int] = None,
) -> Optional[_ScrapflyResponse]:
    """
    通过 Scrapfly 代爬目标 URL。
    未配置 SCRAPFLY_API_KEY 时返回 None，调用方应回退到直连。
    """
    if not SCRAPFLY_API_KEY:
        return None

    full_target = target_url
    if params:
        sep = "&" if "?" in target_url else "?"
        full_target = f"{target_url}{sep}{urlencode(params, doseq=True)}"

    scrapfly_params = {
        "key": SCRAPFLY_API_KEY,
        "url": full_target,
        "asp": "true",
        "country": country,
        "retry": "true",
        "cache": "true",
        "cache_ttl": str(SCRAPFLY_CACHE_TTL),
    }
    if cost_budget is not None:
        scrapfly_params["cost_budget"] = str(cost_budget)
    if render_js:
        scrapfly_params["render_js"] = "true"

    try:
        resp = requests.get(SCRAPFLY_ENDPOINT, params=scrapfly_params, timeout=timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = getattr(resp, "status_code", 0) or 0
            print(f"[Scrapfly] fetch 失败 url={target_url[:80]} err={exc}")
            return _ScrapflyResponse(status, "", full_target, {}, 0, None, "")
        data = resp.json()
        result = data.get("result", {})
        content = result.get("content", "") or ""
        status = result.get("status_code", 200)
        final_url = result.get("url", full_target)
        headers = result.get("response_headers", {})
        cost = _safe_int(resp.headers.get("X-Scrapfly-Api-Cost"), 0)
        remaining = _safe_int(resp.headers.get("X-Scrapfly-Remaining-Api-Credit"), None)
        cache_state = (
            data.get("context", {})
            .get("cache", {})
            .get("state", "")
        )
        return _ScrapflyResponse(status, content, final_url, headers, cost, remaining, cache_state)
    except Exception as exc:
        print(f"[Scrapfly] fetch 失败 url={target_url[:80]} err={exc}")
        return None


SEARCH_URL = "https://html.duckduckgo.com/html/"
BAIDU_SEARCH_URL = "https://www.baidu.com/s"
BING_SEARCH_URL = "https://www.bing.com/search"
SO360_SEARCH_URL = "https://www.so.com/s"
DEFAULT_TIMEOUT = 20  # 中国站点加载慢，12s 太短

# 模拟真实 Chrome 浏览器的请求头，减少被反爬拦截的概率
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
SEARCH_HEADERS_ZH = {
    "User-Agent": _CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
SEARCH_HEADERS_EN = {**SEARCH_HEADERS_ZH, "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}
FETCH_HEADERS = {
    "User-Agent": _CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
# 目标：最终可用资料 10 篇左右
# 经验公式：raw≈24query×4engine×6条=576 → 去重/过滤 → 候选~120 → 抓取~80 → 可用~15
MAX_SEARCH_QUERIES = 24
MAX_SEARCH_REQUESTS = 96
MAX_CANDIDATES_TO_ENRICH = 80
MAX_DISCOVERED_LINKS_PER_SOURCE = 10
MAX_RESEARCH_WORKERS = 8
MIN_USABLE_MATCH_SCORE = 40       # 适度放宽，让边缘相关内容也能入选
MIN_REQUIRED_TERM_MATCH_SCORE = 20
USABLE_ACCESS_STATUSES = ("fetched", "thin_content")  # thin_content 有标题/URL，也有参考价值
KNOWN_BRAND_TERMS = ("彩棠", "花西子", "自然堂", "雅诗兰黛", "谷雨", "完美日记", "毛戈平", "橘朵", "珀莱雅", "薇诺娜", "欧莱雅")
KNOWN_PRODUCT_TERMS = (
    "粉饼", "蜜粉", "散粉", "定妆", "修容", "遮瑕", "腮红",
    "粉底液", "粉底", "底妆", "口红", "唇釉", "眼影", "眉笔", "防晒",
    "修复精华", "修护精华", "精华", "面膜", "面霜", "眼霜", "眼膜", "香水",
)
BRAND_ALIASES = {
    "雅诗兰黛": ("雅诗兰黛集团", "Estee Lauder", "Estée Lauder", "The Estée Lauder Companies"),
    "欧莱雅": ("欧莱雅集团", "L'Oreal", "L’Oréal", "L'Oreal Group"),
    "自然堂": ("伽蓝集团", "CHANDO", "Jala Group"),
    "花西子": ("Florasis",),
    "彩棠": ("TIMAGE",),
    "谷雨": ("Grain Rain",),
    "珀莱雅": ("PROYA",),
    "薇诺娜": ("Winona", "贝泰妮"),
}
PRODUCT_SYNONYMS = {
    "眼霜": ("眼部护理", "眼部精华", "eye cream", "eye care", "eye skincare"),
    "眼膜": ("眼部护理", "eye mask", "eye care"),
    "面膜": ("护肤面膜", "贴片面膜", "facial mask", "skincare mask"),
    "散粉": ("定妆粉", "蜜粉", "loose powder", "setting powder"),
    "粉饼": ("底妆", "pressed powder", "compact powder"),
    "粉底液": ("底妆", "foundation", "liquid foundation"),
    "粉底": ("底妆", "foundation", "base makeup"),
    "修复精华": ("修护精华", "屏障修护", "功效护肤", "repair serum"),
    "修护精华": ("修复精华", "屏障修护", "功效护肤", "repair serum"),
    "精华": ("功效护肤", "serum", "skincare serum"),
    "腮红": ("彩妆", "blush", "color cosmetics"),
}
PRODUCT_CATEGORY_TERMS = {
    "眼霜": ("护肤", "眼部护理", "skincare"),
    "眼膜": ("护肤", "眼部护理", "skincare"),
    "面膜": ("护肤", "功效护肤", "skincare"),
    "面霜": ("护肤", "功效护肤", "skincare"),
    "修复精华": ("护肤", "功效护肤", "屏障修护", "skincare"),
    "修护精华": ("护肤", "功效护肤", "屏障修护", "skincare"),
    "精华": ("护肤", "功效护肤", "skincare"),
    "散粉": ("彩妆", "底妆", "makeup"),
    "粉饼": ("彩妆", "底妆", "makeup"),
    "蜜粉": ("彩妆", "底妆", "makeup"),
    "粉底": ("彩妆", "底妆", "makeup"),
    "粉底液": ("彩妆", "底妆", "makeup"),
    "腮红": ("彩妆", "makeup"),
    "口红": ("彩妆", "makeup"),
    "唇釉": ("彩妆", "makeup"),
    "眼影": ("彩妆", "makeup"),
    "香水": ("香氛", "fragrance", "perfume"),
}
PREFERRED_DOMAINS = (
    "kpmg.com",
    "mckinsey.com",
    "deloitte.com",
    "ey.com",
    "pwc.com",
    "circana.com",
    "statista.com",
    "mintel.com",
    "euromonitor.com",
    "loreal-finance.com",
    "loreal.com",
    "reuters.com",
    "bloomberg.com",
    "forbes.com",
    "wwd.com",
    "voguebusiness.com",
    "businessoffashion.com",
    "jingdaily.com",
    "elcompanies.com",
    "shiseido.com",
    "corp.shiseido.com",
    "coty.com",
    "investors.coty.com",
    "ulta.com",
    "lvmh.com",
    "kering.com",
    "puig.com",
    "china.mintel.com",
    "kantarworldpanel.com",
    "kantar.com",
    "kantar.com.cn",
    "euromonitor.com",
    "nielseniq.cn",
    "nielseniq.com",
    "wwdchina.com",
    "vogue.com",
    "vogue.com.cn",
    "iqingyan.cn",
    "iqyqb.com",
    "jumeili.cn",
    "pinguan.com",
    "mrgcw.com",
    "trendinsight.oceanengine.com",
    "cbndata.com",
    "m.cbndata.com",
    "meiquan.com",
    "nmpa.gov.cn",
    "gov.cn",
    "samr.gov.cn",
    "index.baidu.com",
    "mktindex.com",
    "feigua.cn",
    "bevol.com",
    "bevol.cn",
    "news.qq.com",
    "new.qq.com",
    "qq.com",
    "163.com",
    "news.163.com",
    "36kr.com",
    "yicai.com",
    "datastory.com.cn",
    "sina.com.cn",
    "sina.cn",
    "finance.sina.cn",
)
BLOCKED_DOMAINS = (
    "dirmarketresearch.com",
    "yhresearch.cn",
    "gelonghui.com",
    "cir.cn",
    "qyresearch.com.cn",
    "chinabgao.com",
    "168report.com",
    "sohu.com",
    "book118.com",
    "max.book118.com",
    "wenkh.com.cn",
    "hxrcon.com",
    "maigoo.com",
    "wiseguyreports.com",
    "verifiedmarketreports.com",
    "businessresearchinsights.com",
    "globalmarketmonitor.com.cn",
    "zvzo.com",
    "baogaobox.com",
    "doc.51baogao.cn",
    "gonyn.com",
    "image.so.com",
    "wenda.so.com",
    "wenku.so.com",
    "docin.com",
    "zhihu.com",
    "smzdm.com",
    "post.smzdm.com",
    "baike.so.com",
    "baike.sogou.com",
    "map.360.cn",
    "news.so.com",
    "zhidao.baidu.com",
    "jingyan.baidu.com",
    "hk.cosme.net",
    "cosme.net",
    "360kuai.com",
    "tv.360kan.com",
    "360kan.com",
    "m.360video.so.com",
    # ---- 电商/购物平台（搜出来也是产品listing，无数据价值）----
    "taobao.com",
    "tmall.com",
    "jd.com",
    "mall.jd.com",
    "1688.com",
    "amazon.com",
    "amazon.co.jp",
    "shopee.com",
    "shopee.com.my",
    "shopee.sg",
    "shopee.co.id",
    "shopee.ph",
    "shopee.vn",
    "shopee.tw",
    "lazada.com",
    "lazada.co.id",
    "pchome.com.tw",
    "24h.pchome.com.tw",
    "pcstore.com.tw",
    "momo.com.tw",
    "momoshop.com.tw",
    "aliexpress.com",
    "alibaba.com",
    "pinduoduo.com",
    "dewu.com",
    "poizon.com",
    "beautydechk.com",
    "lookfantastic.com",
    "feelunique.com",
    "sephora.com",
    "ulta.com",
    "boots.com",
    "notino.com",
    "yesstyle.com",
    "stylevana.com",
    "jolse.com",
    "cnpp.cn",
)

# URL 路径级别的电商特征（命中则直接排除，不依赖域名黑名单）
ECOMMERCE_URL_PATTERNS = re.compile(
    r"/(?:search|product|products|listing|listings|shop|store|cart|checkout|buy|order"
    r"|collection|collections|category|categories|item|items|goods|sku|pd|p/\d)"
    r"(?:[/?#]|$)",
    re.IGNORECASE,
)
CURATED_REFERENCE_SEEDS = [
    {
        "title": "L'Oréal Annual Report 2024",
        "url": "https://www.loreal-finance.com/en/annual-report-2024/",
        "source_type": "official",
        "publisher": "loreal-finance.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "makeup", "foundation"),
    },
    {
        "title": "L'Oréal 2024 Annual Results",
        "url": "https://www.loreal-finance.com/eng/news-release/2024-annual-results",
        "source_type": "official",
        "publisher": "loreal-finance.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "makeup", "foundation"),
    },
    {
        "title": "KPMG China Consumer & Retail Industry Analysis 2024H2",
        "url": "https://kpmg.com/cn/en/insights/2025/02/consumer-and-retail-industry-analysis-2024-h2.html",
        "source_type": "institution",
        "publisher": "kpmg.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "retail", "consumer"),
    },
    {
        "title": "Circana US Prestige & Mass Beauty Retail Performance 2025",
        "url": "https://www.circana.com/post/us-prestige-and-mass-beauty-retail-deliver-a-positive-performance-in-2025-circana-reports",
        "source_type": "institution",
        "publisher": "circana.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "prestige", "foundation"),
    },
    {
        "title": "McKinsey State of Fashion: Beauty 2025",
        "url": "https://www.mckinsey.com/industries/consumer-packaged-goods/our-insights/state-of-beauty",
        "source_type": "institution",
        "publisher": "mckinsey.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "makeup", "consumer"),
    },
    {
        "title": "The Estée Lauder Companies Fiscal 2025 Results",
        "url": "https://www.elcompanies.com/en/news-and-media/newsroom/press-releases/2025/08-20-2025-110025649",
        "source_type": "official",
        "publisher": "elcompanies.com",
        "keywords": (
            "美妆", "美业", "彩妆", "粉底", "底妆", "护肤", "眼霜", "眼部护理",
            "雅诗兰黛", "雅诗兰黛集团", "beauty", "prestige", "makeup", "skincare",
            "eye care", "eye cream", "Estee Lauder", "Estée Lauder",
        ),
    },
    {
        "title": "The Estée Lauder Companies Annual Reports",
        "url": "https://www.elcompanies.com/en/%20investors/earnings-and-financials/annual-reports",
        "source_type": "official",
        "publisher": "elcompanies.com",
        "keywords": (
            "美妆", "美业", "彩妆", "粉底", "底妆", "护肤", "眼霜", "眼部护理",
            "雅诗兰黛", "雅诗兰黛集团", "beauty", "prestige", "makeup", "skincare",
            "eye care", "eye cream", "Estee Lauder", "Estée Lauder",
        ),
    },
    {
        "title": "Coty FY25 and Q4 Results",
        "url": "https://investors.coty.com/news-events-and-presentations/news/news-details/2025/Coty-Reports-FY25-and-Q4-Results-Targets-Sequential-LFL-and-EBITDA-Trend-Improvement-in-FY26-Returning-to-Growth-in-2H26/default.aspx",
        "source_type": "official",
        "publisher": "investors.coty.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "makeup", "prestige"),
    },
    {
        "title": "Coty Fiscal 2025 Annual Report Filing",
        "url": "https://investors.coty.com/news-events-and-presentations/news/news-details/2025/Coty-Announces-Filing-of-Annual-Report-on-Form-10-K-for-the-Fiscal-Year-Ended-June-30-2025/default.aspx",
        "source_type": "official",
        "publisher": "investors.coty.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "makeup", "prestige"),
    },
    {
        "title": "Shiseido Integrated Report 2025",
        "url": "https://corp.shiseido.com/en/ir/library/calendar/",
        "source_type": "official",
        "publisher": "corp.shiseido.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "cosmetics", "prestige"),
    },
    {
        "title": "Ulta Beauty Annual Reports & Proxy",
        "url": "https://www.ulta.com/investor/company-information/annual-reports-proxy",
        "source_type": "official",
        "publisher": "ulta.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "retail", "cosmetics"),
    },
    {
        "title": "LVMH 2025 Full Year Results",
        "url": "https://www.lvmh.com/en/financial-calendar/2025-full-year-results",
        "source_type": "official",
        "publisher": "lvmh.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "perfume", "cosmetics"),
    },
    {
        "title": "Puig Integrated Annual Report 2025",
        "url": "https://uploads.puig.com/uploads/PUIG_BRANDS_Puig_Integrated_Annual_Report_2025_eng_65be06fd1b.pdf",
        "source_type": "official",
        "publisher": "puig.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "premium", "fragrance"),
    },
]

USER_REQUESTED_SOURCE_DOMAINS = (
    "china.mintel.com",
    "kantarworldpanel.com",
    "euromonitor.com",
    "nielseniq.cn",
    "wwd.com",
    "wwdchina.com",
    "businessoffashion.com",
    "voguebusiness.com",
    "vogue.com",
    "iqingyan.cn",
    "iqyqb.com",
    "jumeili.cn",
    "pinguan.com",
    "mrgcw.com",
    "trendinsight.oceanengine.com",
    "cbndata.com",
    "m.cbndata.com",
    "meiquan.com",
    "nmpa.gov.cn",
    "samr.gov.cn",
    "index.baidu.com",
    "mktindex.com",
    "feigua.cn",
    "bevol.com",
    "bevol.cn",
)

USER_REQUESTED_SOURCE_ALIASES = (
    "英敏特Mintel",
    "凯度消费者指数",
    "欧睿信息咨询",
    "尼尔森IQ",
    "WWD国际时尚特讯",
    "BoF时装商业评论",
    "Vogue Business",
    "青眼",
    "聚美丽",
    "品观",
    "化妆品观察",
    "巨量算数",
    "算数研究局",
    "CBNData",
    "第一财经商业数据中心",
    "美丽修行",
    "国家药监局",
    "NMPA",
    "百度指数",
    "魔镜市场情报",
    "魔镜洞察",
    "飞瓜数据",
)

REQUESTED_REFERENCE_SEEDS = [
    {
        "title": "英敏特 Mintel 中国洞察",
        "url": "https://china.mintel.com/",
        "source_type": "institution",
        "publisher": "china.mintel.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "consumer", "trend"),
    },
    {
        "title": "凯度消费者指数 Kantar Worldpanel 中国",
        "url": "https://www.kantarworldpanel.com/cn",
        "source_type": "institution",
        "publisher": "kantarworldpanel.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "consumer", "shopper", "retail"),
    },
    {
        "title": "欧睿信息咨询 Euromonitor",
        "url": "https://www.euromonitor.com/",
        "source_type": "institution",
        "publisher": "euromonitor.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "market", "consumer"),
    },
    {
        "title": "尼尔森IQ 中国美妆个护行业趋势与展望报告",
        "url": "https://nielseniq.cn/global/zh/insights/report/2024/niq-2024-china-beauty-and-personal-insight/",
        "source_type": "institution",
        "publisher": "nielseniq.cn",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "personal care", "consumer"),
    },
    {
        "title": "WWD 国际时尚特讯",
        "url": "https://wwd.com/",
        "source_type": "media",
        "publisher": "wwd.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "fashion", "business"),
    },
    {
        "title": "BoF 时装商业评论",
        "url": "https://www.businessoffashion.com/",
        "source_type": "media",
        "publisher": "businessoffashion.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "fashion", "business"),
    },
    {
        "title": "Vogue Business",
        "url": "https://www.vogue.com/business",
        "source_type": "media",
        "publisher": "vogue.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "beauty", "fashion", "business"),
    },
    {
        "title": "青眼",
        "url": "https://www.iqingyan.cn/",
        "source_type": "media",
        "publisher": "iqingyan.cn",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "化妆品", "行业"),
    },
    {
        "title": "青眼情报",
        "url": "https://www.iqyqb.com/index",
        "source_type": "institution",
        "publisher": "iqyqb.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "化妆品", "行业", "数据"),
    },
    {
        "title": "聚美丽",
        "url": "https://www.jumeili.cn/about/",
        "source_type": "media",
        "publisher": "jumeili.cn",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "化妆品", "行业"),
    },
    {
        "title": "品观 CiE / 化妆品观察",
        "url": "https://cie.pinguan.com/about-us",
        "source_type": "media",
        "publisher": "cie.pinguan.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "化妆品", "行业"),
    },
    {
        "title": "巨量算数 算数研究局",
        "url": "https://trendinsight.oceanengine.com/foresee/arithmetic-report",
        "source_type": "institution",
        "publisher": "trendinsight.oceanengine.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "抖音", "趋势", "人群"),
    },
    {
        "title": "CBNData 第一财经商业数据中心",
        "url": "https://m.cbndata.com/",
        "source_type": "institution",
        "publisher": "m.cbndata.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "消费", "人群", "趋势"),
    },
    {
        "title": "美丽修行",
        "url": "https://www.bevol.com/",
        "source_type": "institution",
        "publisher": "bevol.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "化妆品", "成分", "产品"),
    },
    {
        "title": "国家药监局化妆品监管",
        "url": "https://www.nmpa.gov.cn/hzhp/index.html",
        "source_type": "official",
        "publisher": "nmpa.gov.cn",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "化妆品", "监管", "备案"),
    },
    {
        "title": "百度指数",
        "url": "https://index.baidu.com/",
        "source_type": "institution",
        "publisher": "index.baidu.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "搜索", "指数", "趋势"),
    },
    {
        "title": "魔镜洞察美妆护肤线上市场趋势洞察",
        "url": "https://hometest.mktindex.com/research/notebook/article_20260304",
        "source_type": "institution",
        "publisher": "mktindex.com",
        "keywords": ("美妆", "美业", "彩妆", "粉底", "底妆", "线上", "市场", "趋势"),
    },
]


class DuckDuckGoResultParser(HTMLParser):
    """DuckDuckGo HTML 搜索结果解析器。

    策略：
    1. 优先匹配 class 含 "result__a" / "result-link" 的 <a>（精准）
    2. 若主策略 0 命中，降级为"所有指向外部站点的非 DDG 链接"（fallback）
    """

    # DDG 自身会在 HTML 里更换类名，多备几个
    _RESULT_LINK_CLASSES = {"result__a", "result-link", "result__url"}

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._all_external: List[Dict[str, str]] = []   # fallback 池
        self._current_href: Optional[str] = None
        self._current_text: List[str] = []
        self._capture_title = False
        self._capture_any = False   # fallback 模式的捕获标志

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href", "") or ""
        class_name = attrs_dict.get("class", "") or ""

        # 主策略：命中已知 result class
        if any(cls in class_name for cls in self._RESULT_LINK_CLASSES):
            self._current_href = href
            self._current_text = []
            self._capture_title = True
            return

        # fallback：收集所有外部链接（非 DDG 域名，以 http 开头）
        if href.startswith("http") and "duckduckgo.com" not in href:
            self._capture_any = True
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if (self._capture_title or self._capture_any) and data.strip():
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        title = " ".join(self._current_text).strip()
        if self._capture_title and self._current_href and title:
            self.results.append({
                "title": clean_text(unescape(title)),
                "url": normalize_search_result_url(self._current_href),
            })
        elif self._capture_any and self._current_href and title and len(title) >= 5:
            self._all_external.append({
                "title": clean_text(unescape(title)),
                "url": normalize_search_result_url(self._current_href),
            })
        self._current_href = None
        self._current_text = []
        self._capture_title = False
        self._capture_any = False

    def get_results(self) -> List[Dict[str, str]]:
        """主策略有结果用主策略，否则用 fallback（去掉明显的导航/广告链接）。"""
        if self.results:
            return self.results
        # fallback：过滤只有 1-2 个词、明显是导航的链接
        _NAV_PATTERNS = re.compile(
            r"^(about|contact|login|register|privacy|terms|home|more|next|search"
            r"|关于|联系|登录|注册|更多|下一页|首页)$",
            re.IGNORECASE,
        )
        filtered = [
            r for r in self._all_external
            if len(r["title"]) >= 6 and not _NAV_PATTERNS.match(r["title"].strip())
        ]
        seen_urls: set = set()
        deduped = []
        for r in filtered:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                deduped.append(r)
        return deduped[:12]


class BaiduResultParser(HTMLParser):
    """百度搜索结果解析器。

    百度 HTML 结果链接两种形态：
    - 直接 URL：href="https://example.com/..."  → 直接采用
    - 跳转链接：href="https://www.baidu.com/link?url=..."  → 过滤掉（无法解码且会被block）
    - 相对跳转：href="/link?url=..."  → 同上，过滤
    只保留直接指向外站的 URL，避免 baidu.com 中转失败。
    """

    _BAIDU_REDIRECT = re.compile(r"(baidu\.com/link\?|/link\?url=)", re.IGNORECASE)

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._href: Optional[str] = None
        self._text: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href", "") or ""
        # 过滤百度跳转链接；只保留直接外部 URL
        if href.startswith("http") and not self._BAIDU_REDIRECT.search(href):
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href and data.strip():
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            title = clean_text(" ".join(self._text))
            if title and len(title) >= 4:
                self.results.append({"title": title, "url": self._href})
            self._href = None
            self._text = []


class BingResultParser(HTMLParser):
    """Bing 搜索结果解析器。

    策略：
    1. 主策略：在 <h2> 内的 <a>（Bing 的搜索结果标题结构）
    2. 备策略：class 含 "b_algo" 块内的第一个外部 <a>
    3. fallback：所有外部链接（与 DDG fallback 相同）
    """

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._all_external: List[Dict[str, str]] = []
        self._inside_result_heading = False
        self._inside_b_algo = False
        self._href: Optional[str] = None
        self._text: List[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "") or ""
        if tag == "h2":
            self._inside_result_heading = True
        if "b_algo" in cls:
            self._inside_b_algo = True
        if tag != "a":
            return
        href = attrs_dict.get("href", "") or ""
        if not href.startswith("http"):
            return
        # 主/备策略
        if self._inside_result_heading or self._inside_b_algo:
            if "bing.com" not in href:
                self._href = href
                self._text = []
        # fallback：所有外部链接
        if "bing.com" not in href:
            self._all_external.append({"_href": href, "_text_start": len(self._text)})

    def handle_data(self, data: str) -> None:
        if self._href and data.strip():
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            title = clean_text(" ".join(self._text))
            if title and len(title) >= 4:
                self.results.append({
                    "title": title,
                    "url": normalize_search_result_url(self._href),
                })
            self._href = None
            self._text = []
        if tag == "h2":
            self._inside_result_heading = False
        if tag == "div":
            self._inside_b_algo = False

    def get_results(self) -> List[Dict[str, str]]:
        if self.results:
            return self.results
        # fallback: 用 _all_external 过滤后返回
        seen: set = set()
        out = []
        for item in self._all_external:
            url = normalize_search_result_url(item.get("_href", ""))
            if url and url not in seen:
                seen.add(url)
                out.append({"title": url, "url": url})
        return out[:12]


class GenericSearchResultParser(HTMLParser):
    """通用搜索结果解析器（用于 So360 等）。

    相比原版加了过滤：
    - 链接文本太短（< 5字符）→ 跳过（导航按钮）
    - 链接 URL 属于同域 → 跳过（站内导航）
    """

    _NAV_SKIP_RE = re.compile(
        r"(首页|登录|注册|关于|联系|隐私|条款|返回|更多|下一页|搜索|home|about|contact|login|next|more|privacy|terms)",
        re.IGNORECASE,
    )

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._base_host = urlparse(base_url).netloc.lower()
        self.results: List[Dict[str, str]] = []
        self._href: Optional[str] = None
        self._text: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href", "") or ""
        if href.startswith("http") or href.startswith("/"):
            resolved = urljoin(self.base_url, href)
            # 过滤同域链接（站内导航）
            if urlparse(resolved).netloc.lower() == self._base_host:
                return
            self._href = resolved
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href and data.strip():
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            title = clean_text(" ".join(self._text))
            if title and len(title) >= 5 and not self._NAV_SKIP_RE.search(title):
                self.results.append({
                    "title": title,
                    "url": normalize_search_result_url(self._href),
                })
            self._href = None
            self._text = []


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self._href: Optional[str] = None
        self._text: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href and data.strip():
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = clean_text(" ".join(self._text))
            self.links.append({"href": self._href, "title": text})
            self._href = None
            self._text = []


def normalize_search_result_url(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        target = parse_qs(parsed.query).get("u")
        if target:
            encoded = unquote(target[0])
            if encoded.startswith("a1"):
                encoded = encoded[2:]
            try:
                padded = encoded + "=" * (-len(encoded) % 4)
                decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
                if decoded.startswith("http"):
                    return decoded
            except (ValueError, UnicodeDecodeError):
                return url
    return url


def clean_text(text: str) -> str:
    if not text:
        return ""

    cleaned = unescape(text).strip()
    mojibake_markers = ("â", "Ã", "â", "Â", "â€™", "â€œ", "â€", "�")
    if any(marker in cleaned for marker in mojibake_markers):
        for encoding in ("latin-1", "cp1252"):
            try:
                repaired = cleaned.encode(encoding).decode("utf-8")
                if repaired:
                    cleaned = repaired
                    break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue

    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_visible_text(html: str) -> str:
    """从 HTML 中提取正文可见文本，优先剥离导航/页脚/侧边栏噪声。

    策略：
    1. 删除 script / style / noscript
    2. 优先提取 <main> / <article> / 带 content|article|post class 的 div
       （这些是正文区域，避免把导航栏/footer 混入）
    3. 如果找不到，删除 nav/header/footer/aside 再全文提取（兜底）
    """
    if not html:
        return ""

    # Step 1：删除脚本/样式/模板
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<noscript[\s\S]*?</noscript>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<!--[\s\S]*?-->", " ", cleaned)

    # Step 2：尝试提取语义正文标签
    _MAIN_BLOCK_RE = re.compile(
        r"<(main|article)(?:\s[^>]*)?>[\s\S]*?</\1>",
        re.IGNORECASE,
    )
    main_blocks = _MAIN_BLOCK_RE.findall(cleaned)
    if not main_blocks:
        # 尝试带 content/article/post class 的 div（最多向后匹配 20000 字符）
        _CONTENT_DIV_RE = re.compile(
            r'<div[^>]+class=["\'][^"\']*(?:content|article|post|entry|detail|body)[^"\']*["\'][^>]*>'
            r'([\s\S]{200,20000}?)</div>',
            re.IGNORECASE,
        )
        content_match = _CONTENT_DIV_RE.search(cleaned)
        if content_match:
            main_blocks = [content_match.group(0)]

    if main_blocks:
        # 拼接所有正文块
        body_html = " ".join(main_blocks)
        text = re.sub(r"<[^>]+>", " ", body_html)
        result = clean_text(text)
        if len(result) >= 80:
            return result

    # Step 3：兜底 — 剥掉 nav/header/footer/aside 再全文提取
    for tag in ("nav", "header", "footer", "aside"):
        cleaned = re.sub(rf"<{tag}(?:\s[^>]*)?>[\s\S]*?</{tag}>", " ", cleaned, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", cleaned)
    return clean_text(text)


def extract_pdf_text(content: bytes, max_pages: int = 5) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        page_texts = []
        for page in reader.pages[:max_pages]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                page_texts.append(page_text)
        return clean_text(" ".join(page_texts))
    except Exception:
        return ""


def is_relevant_source_link(title: str, url: str, topic: str) -> bool:
    text = f"{title} {url}".lower()
    if is_entertainment_content(title, url):
        return False
    required_terms = extract_required_topic_terms(topic)
    content_markers = (
        "报告", "白皮书", "洞察", "趋势", "市场", "美妆", "彩妆", "粉底", "护肤",
        "insight", "report", "research", "trend", "beauty", "makeup", "cosmetic",
        "foundation", "market", "article", "notebook",
    )
    navigation_markers = (
        "about", "contact", "login", "register", "career", "privacy", "terms",
        "关于我们", "联系我们", "登录", "注册", "隐私", "招聘",
    )
    if any(marker in text for marker in navigation_markers):
        return False
    if required_terms:
        return any(term.lower() in text for term in required_terms)
    if any(marker in text for marker in content_markers):
        return True
    return any(term in text for term in extract_topic_terms(topic))


def discover_links_from_html(
    html: str, base_url: str, publisher: str, topic: str
) -> List[Dict[str, str]]:
    parser = LinkParser()
    parser.feed(html or "")
    discovered: List[Dict[str, str]] = []
    seen = set()
    for link in parser.links:
        url = urljoin(base_url, link.get("href", ""))
        host = extract_publisher(url)
        if not domain_matches(host, publisher):
            continue
        if not is_allowed_result_url(url):
            continue
        if url in seen:
            continue
        title = clean_text(link.get("title", ""))
        if not title or not is_relevant_source_link(title, url, topic):
            continue
        seen.add(url)
        discovered.append({"title": title, "url": url})
    return discovered[:MAX_DISCOVERED_LINKS_PER_SOURCE]


def discover_source_candidates(
    seed: Dict[str, str], session: requests.Session, timeout: int, topic: str
) -> List[Dict[str, str]]:
    try:
        response = session.get(seed["url"], timeout=timeout)
        if response.status_code >= 400:
            return []
    except requests.RequestException:
        return []

    candidates = []
    for link in discover_links_from_html(
        response.text,
        seed["url"],
        seed.get("publisher", extract_publisher(seed.get("url", ""))),
        topic,
    ):
        candidates.append(
            {
                "title": link["title"],
                "url": link["url"],
                "source_type": seed.get("source_type", infer_source_type(link["url"], link["title"])),
                "publisher": extract_publisher(link["url"]),
                "published_at": None,
                "summary": "",
                "discovered_from": seed.get("url", ""),
            }
        )
    return candidates


def classify_access_status(raw_html: str, visible_text_length: int) -> str:
    """判断页面的可读状态。

    改进原则：
    1. 有足够正文（>=200字符）就认为可读，哪怕页面含订阅词汇（很多媒体在页脚有"订阅资讯"）
    2. 真正的付费墙：可见文本极少（<120字符）且含有强付费墙信号
    3. 登录墙：检测"必须登录才能查看"的明确表达
    4. 动态页：JS框架渲染，静态 HTML 几乎没内容
    """
    raw = (raw_html or "").lower()

    # 有足够内容 → 直接认为可读，不管页面其他元素写了什么
    if visible_text_length >= 200:
        return "fetched"

    # 明确登录墙（强信号短语）
    login_hard_signals = (
        "请登录后查看", "登录后才能", "login required", "sign in to view",
        "log in to read", "请先登录", "need to log in",
    )
    if any(s in raw for s in login_hard_signals):
        return "login_required"

    # 真正的付费墙：极少内容 + 强付费信号
    paywall_hard_signals = (
        "subscribe to read", "subscribe to continue", "paywall",
        "purchase to read", "buy this article",
        "订阅后阅读全文", "订阅查看全文", "付费阅读", "付费内容",
        "开通会员查看", "购买后可看",
    )
    if visible_text_length < 120 and any(s in raw for s in paywall_hard_signals):
        return "paywalled"

    # 动态前端应用
    if visible_text_length < 80 and any(
        marker in raw for marker in ("__nuxt__", "__next_data__", "id=\"app\"", "id='app'")
    ):
        return "dynamic_required"

    if visible_text_length < 80:
        return "thin_content"

    return "fetched"


def is_entertainment_content(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts).lower()
    if not text:
        return False
    entertainment_markers = (
        "qq音乐", "网易云音乐", "酷狗音乐", "酷我音乐", "spotify", "apple music",
        "歌曲", "歌词", "歌单", "专辑", "单曲", "音乐", "试听", "播放",
        "lyric", "lyrics", "album", "artist", "track", "playlist", "music video",
        "/song", "/songdetail", "/album", "/playlist", "/lyrics", "/mv",
        "music.163.com", "y.qq.com", "kugou.com", "kuwo.cn",
    )
    return any(marker in text for marker in entertainment_markers)


def is_remembered_bad_source(source: str, remembered_bad_sources: Optional[List[str]]) -> bool:
    normalized = (source or "").lower().strip()
    if not normalized or not remembered_bad_sources:
        return False
    for bad_source in remembered_bad_sources:
        bad = (bad_source or "").lower().strip()
        if not bad:
            continue
        if "://" in bad:
            if bad in normalized:
                return True
        elif domain_matches(normalized, bad) or bad in normalized:
            return True
    return False


def is_allowed_result_url(url: str) -> bool:
    if not url:
        return False
    normalized = url.lower()
    if any(blocked in normalized for blocked in ("duckduckgo.com", "javascript:", "/y.js", "/news.js")):
        return False
    if is_entertainment_content(url):
        return False
    if any(blocked_domain in normalized for blocked_domain in BLOCKED_DOMAINS):
        return False
    if extract_publisher(url) == "baidu.com":
        return False
    # URL 路径级别电商特征：search?keyword=、/products/、/cart/ 等 → 直接排除
    parsed_path = urlparse(url).path
    if ECOMMERCE_URL_PATTERNS.search(parsed_path):
        # 可信媒体域名的 /search/ 路径不在此限（站内搜索，不是电商listing）
        publisher_from_url = extract_publisher(url)
        if not is_preferred_publisher(publisher_from_url):
            return False
    return True


def domain_matches(host_or_publisher: str, domain: str) -> bool:
    normalized = (host_or_publisher or "").lower().strip()
    normalized = normalized.removeprefix("www.")
    domain = (domain or "").lower().strip().removeprefix("www.")
    return normalized == domain or normalized.endswith(f".{domain}")


def is_preferred_publisher(publisher: str) -> bool:
    normalized = (publisher or "").lower()
    return any(domain_matches(normalized, domain) for domain in PREFERRED_DOMAINS)


def is_user_requested_source(publisher: str) -> bool:
    normalized = (publisher or "").lower()
    return any(domain_matches(normalized, domain) for domain in USER_REQUESTED_SOURCE_DOMAINS)


def _topic_category_terms(product_terms: List[str]) -> List[str]:
    categories: List[str] = []
    for term in product_terms:
        categories.extend(PRODUCT_CATEGORY_TERMS.get(term, ()))
    return list(dict.fromkeys(categories))


def _broad_seed_category_terms(product_terms: List[str]) -> List[str]:
    broad_terms = {"护肤", "彩妆", "skincare", "makeup"}
    categories = [term for term in _topic_category_terms(product_terms) if term in broad_terms]
    if product_terms:
        categories.extend(["美妆", "beauty"])
    return list(dict.fromkeys(categories))


def get_curated_reference_seeds(topic: str) -> List[Dict[str, str]]:
    normalized_topic = (topic or "").lower()
    required_terms = extract_required_topic_terms(topic)
    matched = []
    for seed in CURATED_REFERENCE_SEEDS:
        seed_text = " ".join(
            [
                seed.get("title", ""),
                seed.get("url", ""),
                seed.get("publisher", ""),
                " ".join(seed.get("keywords", ())),
            ]
        ).lower()
        required_groups = extract_required_topic_groups(topic)
        category_terms = _broad_seed_category_terms(required_groups.get("product", []))
        has_required_term = any(term.lower() in seed_text for term in required_terms)
        has_category_term = any(term.lower() in seed_text for term in category_terms)
        if required_terms and not (has_required_term or has_category_term):
            continue
        if any(keyword.lower() in normalized_topic for keyword in seed.get("keywords", ())) or has_category_term:
            matched.append({k: v for k, v in seed.items() if k != "keywords"})
    return matched


def enrich_reference(candidate: Dict[str, str], session: requests.Session, timeout: int) -> Optional[Dict[str, str]]:
    import time as _time
    enriched = dict(candidate)
    page = None
    if SCRAPFLY_API_KEY:
        url_lower = enriched["url"].lower().split("?", 1)[0]
        if not url_lower.endswith(".pdf"):
            page = _scrapfly_fetch(
                enriched["url"],
                timeout=timeout,
                country="cn",
                cost_budget=SCRAPFLY_COST_BUDGET_PAGE,
            )

    if page is None:
        for attempt in range(2):
            try:
                page = session.get(enriched["url"], timeout=timeout, headers=FETCH_HEADERS)
                break
            except requests.Timeout:
                if attempt == 0:
                    _time.sleep(1)
            except requests.RequestException:
                break
    try:
        if page is None:
            raise requests.RequestException("all retries failed")
        if page.status_code >= 400:
            return None
        if hasattr(page, "cost"):
            enriched["scrapfly_cost"] = getattr(page, "cost", 0)
            enriched["scrapfly_remaining_credit"] = getattr(page, "remaining_credit", None)
            enriched["scrapfly_cache_state"] = getattr(page, "cache_state", "")
        if page.url and page.url != enriched.get("url"):
            if not is_allowed_result_url(page.url):
                return None
            enriched["url"] = page.url
            enriched["publisher"] = extract_publisher(page.url)
            enriched["source_type"] = infer_source_type(page.url, enriched.get("title", ""))
        content_type = page.headers.get("content-type", "").lower()
        is_pdf = "application/pdf" in content_type or enriched["url"].lower().split("?", 1)[0].endswith(".pdf")
        if is_pdf:
            content_text = extract_pdf_text(page.content)
            enriched["published_at"] = enriched.get("published_at")
            enriched["summary"] = content_text[:240] if content_text else enriched.get("summary", enriched.get("title", ""))
            enriched["content_text"] = content_text
            enriched["content_excerpt"] = content_text[:360]
            enriched["access_status"] = "fetched" if content_text else "pdf_unparsed"
        else:
            html = page.text
            enriched["published_at"] = extract_published_at(html)
            enriched["summary"] = extract_summary(html)
            content_text = extract_visible_text(html)
            enriched["content_text"] = content_text
            enriched["content_excerpt"] = content_text[:360]
            enriched["access_status"] = classify_access_status(html, len(content_text))
    except requests.RequestException:
        enriched["published_at"] = enriched.get("published_at")
        enriched["summary"] = enriched.get("summary", enriched.get("title", ""))
        fallback_text = " ".join(
            [
                enriched.get("title", ""),
                enriched.get("summary", ""),
                enriched.get("url", ""),
            ]
        )
        enriched["content_text"] = fallback_text
        enriched["content_excerpt"] = fallback_text[:360]
        enriched["access_status"] = "request_failed"
    return enriched


def infer_source_type(url: str, title: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    title_lower = title.lower()

    official_markers = (
        ".gov",
        ".edu",
        ".org.cn",
        "investor",
        "annual report",
        "official",
        "官网",
        "财报",
    )
    institution_domains = (
        "kpmg.com",
        "mckinsey.com",
        "deloitte.com",
        "ey.com",
        "pwc.com",
        "statista.com",
        "circana.com",
        "mintel.com",
        "euromonitor.com",
    )
    institution_markers = (
        "kantar",
        "irsglobal",
        "艾瑞",
        "德勤",
        "麦肯锡",
        "毕马威",
        "尼尔森",
    )
    media_markers = (
        "reuters",
        "bloomberg",
        "forbes",
        "wwd",
        "businessoffashion",
        "voguebusiness",
        "jingdaily",
        "第一财经",
        "界面",
        "36kr",
    )

    if any(marker in host or marker in title_lower for marker in official_markers):
        return "official"
    if any(domain_matches(host, domain) for domain in institution_domains):
        return "institution"
    if any(marker in host or marker in title_lower for marker in institution_markers):
        return "institution"
    if any(marker in host or marker in title_lower for marker in media_markers):
        return "media"
    return "media"


def extract_publisher(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def extract_published_at(html: str) -> Optional[str]:
    patterns = [
        r'property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']',
        r'name=["\']pubdate["\']\s+content=["\']([^"\']+)["\']',
        r'name=["\']publishdate["\']\s+content=["\']([^"\']+)["\']',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{4}/\d{2}/\d{2})',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).strip()
        raw = raw.replace("/", "-")
        if "T" in raw:
            raw = raw.split("T", 1)[0]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return raw
    return None


def extract_summary(html: str) -> str:
    meta_patterns = [
        r'name=["\']description["\']\s+content=["\']([^"\']+)["\']',
        r'property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(1))

    text = extract_visible_text(html)
    return text[:240]


def build_search_queries(topic: str) -> List[str]:
    """生成精准查询：每条 query 都强制包含用户/文章关键词。

    设计原则：
    - 所有 query 都以用户/文章的真实关键词为锚（extract_required_topic_terms）
    - 只换搜索后缀，不做跨话题泛化
    - 目标：24 条精准变体 × 4 引擎 = ~96 次请求，最终可用资料 10 篇左右
    """
    topic = re.sub(r"\s+", " ", topic or "").strip()
    if not topic:
        return []
    topic = topic[:80]
    compact_topic = re.sub(r"[【】\[\]（）()]", " ", topic)
    compact_topic = re.sub(r"\s+", " ", compact_topic).strip()

    required_terms = extract_required_topic_terms(compact_topic)
    year = datetime.now().year
    prev_year = year - 1

    # 没提取到具体关键词：只做 1 条原样查询，避免泛化噪声
    if not required_terms:
        return [compact_topic] if compact_topic else []

    required_groups = extract_required_topic_groups(compact_topic)
    grouped_terms = []
    for group_name in ("brand", "product"):
        grouped_terms.extend(required_groups.get(group_name, []))
    grouped_terms.extend(required_terms)
    ordered_terms = list(dict.fromkeys(grouped_terms))

    # 核心词：最多取前 3 个，且优先品牌+品类组合。
    # 省积分模式只会跑前几条 query，所以必须在前 5 条里覆盖：组合、品牌、品类。
    core_terms = ordered_terms[:3]
    first_term = f'"{core_terms[0]}"'
    rest_terms = " ".join(core_terms[1:])
    core = (first_term + " " + rest_terms).strip()

    if len(core_terms) == 1:
        queries: List[str] = [
            first_term,
            f"{first_term} 市场",
            f"{first_term} 数据",
            f"{first_term} 行业",
            f"{first_term} 报告",
            f"{first_term} 白皮书",
            f"{first_term} 趋势",
            f"{first_term} 洞察",
            f"{first_term} 分析",
            f"{first_term} 研究",
            f"{first_term} 消费者",
            f"{first_term} {year}",
            f"{first_term} {prev_year}",
        ]
    else:
        standalone_terms = [f'"{term}"' for term in core_terms]
        queries = [
            core,
            f"{core} 市场",
            f"{core} 数据",
            f"{core} 报告",
            f"{core} 行业",
            standalone_terms[0],
            standalone_terms[1],
            f"{standalone_terms[0]} 市场",
            f"{standalone_terms[1]} 市场",
            f"{standalone_terms[0]} 数据",
            f"{standalone_terms[1]} 数据",
            f"{core} 白皮书",
            f"{core} 趋势",
            f"{core} 洞察",
            f"{core} 分析",
            f"{core} 研究",
            f"{core} 消费者",
            f"{core} {year}",
            f"{core} {prev_year}",
        ]

    brand_terms = required_groups.get("brand", [])[:2]
    product_terms = required_groups.get("product", [])[:2]
    category_terms = _topic_category_terms(product_terms)
    expansion_queries: List[str] = []
    for brand in brand_terms:
        aliases = list(BRAND_ALIASES.get(brand, ()))[:4]
        for product in product_terms:
            product_synonyms = list(PRODUCT_SYNONYMS.get(product, ()))[:4]
            if brand == "雅诗兰黛":
                expansion_queries.extend(
                    [
                        f"site:elcompanies.com {brand} {product}",
                        f"site:elcompanies.com Estee Lauder {product}",
                    ]
                )
            if brand == "欧莱雅":
                expansion_queries.append(f"site:loreal-finance.com {brand} {product}")
            if aliases:
                expansion_queries.append(f'"{aliases[0]}" {product} 报告')
            if product_synonyms:
                expansion_queries.append(f'"{brand}" {product_synonyms[0]} 报告')
            for category in category_terms[:3]:
                expansion_queries.extend(
                    [
                        f'"{product}" {category} 市场 报告',
                        f'"{category}" 美妆 数据 {prev_year}',
                        f'"{brand}" {category} 报告',
                    ]
                )
            expansion_queries.extend(
                [
                    f'"{brand}" {product} 行业报告',
                    f'"{brand}" {product} 市场数据',
                    f'"{brand}" {product} 消费趋势',
                    f'"{brand}" {product} site:36kr.com',
                    f'"{brand}" {product} site:news.qq.com',
                    f'"{brand}" {product} site:finance.sina.com.cn',
                    f'"{brand}" {product} site:fxbaogao.com',
                ]
            )
            for synonym in product_synonyms[:2]:
                expansion_queries.append(f'"{brand}" {synonym} 报告')
            for alias in aliases[:2]:
                expansion_queries.extend(
                    [
                        f'"{alias}" {product} market report',
                        f'"{alias}" skincare annual report',
                    ]
                )
                if product_synonyms:
                    expansion_queries.append(f'"{alias}" {product_synonyms[0]} market data')
            if brand == "雅诗兰黛":
                expansion_queries.extend(
                    [
                        f"site:elcompanies.com Estee Lauder skincare annual report",
                        f"site:elcompanies.com Estee Lauder {product} eye care",
                        f"prestige skincare China {product} market report",
                    ]
                )
            if brand == "欧莱雅":
                expansion_queries.extend(
                    [
                        f"site:loreal-finance.com L'Oreal skincare annual report",
                        f"site:loreal.com.cn 欧莱雅 {product} 报告",
                    ]
                )

    if expansion_queries:
        # 先保留组合词核心意图，再插入品类/英文别名/官方财报方向，避免预算截止前只搜到产品页。
        queries = queries[:4] + expansion_queries + queries[4:]

    queries.extend(
        [
            f"{core} 数据 市场",
            f"{core} 趋势 分析",
            f"{core} 品牌",
            f"{core} 规模",
            f"{core} 增长",
            f"{core} 销售额",
            f"{core} 竞争",
            # ── 指定行业媒体来源
            f"{core} site:cbndata.com OR site:qingyan.com OR site:jumeili.cn",
            f"{core} site:36kr.com OR site:yicai.com OR site:163.com",
        ]
    )

    return list(dict.fromkeys(queries))[:MAX_SEARCH_QUERIES]


def _safe_search(session: requests.Session, url: str, params: dict, timeout: int, headers: dict) -> str:
    """带重试的搜索请求（最多 2 次，指数退避）。返回 response.text，失败返回空串。"""
    if SCRAPFLY_API_KEY:
        for attempt in range(SCRAPFLY_SEARCH_RETRIES):
            with _SCRAPFLY_SEARCH_SEMAPHORE:
                resp = _scrapfly_fetch(
                    url,
                    params=params,
                    timeout=timeout,
                    country="cn",
                    cost_budget=SCRAPFLY_COST_BUDGET_SEARCH,
                )
            if resp and resp.status_code < 400:
                print(
                    "[Research][Scrapfly] "
                    f"search cost={resp.cost} cache={resp.cache_state or '-'} "
                    f"remaining={resp.remaining_credit if resp.remaining_credit is not None else '-'} "
                    f"url={urlparse(url).netloc}"
                )
                return resp.text
            should_retry = bool(resp and resp.status_code in (429, 500, 502, 503, 504))
            if not should_retry:
                return ""
            if attempt < SCRAPFLY_SEARCH_RETRIES - 1:
                delay = SCRAPFLY_SEARCH_BACKOFF_SECONDS ** (attempt + 1)
                print(
                    "[Research][Scrapfly] "
                    f"search retry={attempt + 1}/{SCRAPFLY_SEARCH_RETRIES - 1} "
                    f"url={urlparse(url).netloc} wait={delay}s"
                )
                time.sleep(delay)
        return ""

    for attempt in range(2):
        try:
            resp = session.get(url, params=params, timeout=timeout, headers=headers)
            if resp.status_code == 429:
                # 限流：退避后重试
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.text
        except Exception:
            if attempt == 0:
                time.sleep(1.5)
    return ""


def search_duckduckgo(query: str, session: requests.Session, timeout: int) -> List[Dict[str, str]]:
    html = _safe_search(session, SEARCH_URL, {"q": query}, timeout, SEARCH_HEADERS_EN)
    if not html:
        return []
    parser = DuckDuckGoResultParser()
    parser.feed(html)
    return parser.get_results()


def search_baidu(query: str, session: requests.Session, timeout: int) -> List[Dict[str, str]]:
    html = _safe_search(session, BAIDU_SEARCH_URL, {"wd": query}, timeout, SEARCH_HEADERS_ZH)
    if not html:
        return []
    parser = BaiduResultParser()
    parser.feed(html)
    return parser.results


def search_bing(query: str, session: requests.Session, timeout: int) -> List[Dict[str, str]]:
    html = _safe_search(session, BING_SEARCH_URL, {"q": query}, timeout, SEARCH_HEADERS_ZH)
    if not html:
        return []
    parser = BingResultParser()
    parser.feed(html)
    return parser.get_results()


def search_so360(query: str, session: requests.Session, timeout: int) -> List[Dict[str, str]]:
    html = _safe_search(session, SO360_SEARCH_URL, {"q": query}, timeout, SEARCH_HEADERS_ZH)
    if not html:
        return []
    parser = GenericSearchResultParser(SO360_SEARCH_URL)
    parser.feed(html)
    return parser.results


def extract_topic_terms(topic: str) -> List[str]:
    raw_terms = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", topic or "")
    expanded = list(raw_terms)
    synonym_map = {
        "高端": ["高端", "prestige", "premium"],
        "粉底": ["粉底", "底妆", "foundation", "base makeup"],
        "粉底液": ["粉底液", "粉底", "foundation"],
        "底妆": ["底妆", "粉底", "foundation", "base makeup"],
        "美妆": ["美妆", "美业", "彩妆", "beauty", "makeup", "cosmetics"],
        "美业": ["美业", "美妆", "beauty", "cosmetics"],
        "彩妆": ["彩妆", "makeup", "color cosmetics"],
        "市场": ["市场", "行业", "market", "industry"],
        "趋势": ["趋势", "洞察", "报告", "trend", "insight", "report"],
        "消费者": ["消费者", "人群", "consumer", "shopper"],
    }
    for term in raw_terms:
        expanded.extend(synonym_map.get(term, []))
    for term, synonyms in synonym_map.items():
        if term in (topic or ""):
            expanded.extend([term, *synonyms])
    if any(term in (topic or "") for term in ("美妆", "美业", "粉底", "底妆", "彩妆")):
        expanded.extend(["美妆", "化妆品", "护肤", "彩妆", "beauty", "cosmetics", "makeup"])
    return [term.lower() for term in dict.fromkeys(expanded) if len(term.strip()) >= 2]


def extract_required_topic_terms(topic: str) -> List[str]:
    topic = topic or ""
    stop_terms = {
        "数据", "分析", "数据分析", "报告", "市场", "趋势", "行业", "美妆", "美业",
        "化妆品", "研究", "白皮书", "中国", "2024", "2025", "2026",
        # UI / 前端投喂的结构标签，不是主题词
        "文字输入", "文字", "文本", "输入", "粘贴", "粘贴文本",
        "文件", "文件上传", "上传", "数据文件", "数据文件摘要", "摘要",
        "图片", "图片上传", "附件", "内容",
    }
    # 去掉 proxy.py 里拼接的 【文字输入】/【文件上传】… 标签本身（整段，而非只剥括号）
    topic = re.sub(r"【[^【】]{0,20}】", " ", topic)
    known_specific_terms = (*KNOWN_BRAND_TERMS, *KNOWN_PRODUCT_TERMS)
    required = []
    raw_terms = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", topic)
    product_suffixes = sorted(KNOWN_PRODUCT_TERMS, key=len, reverse=True)
    for term in raw_terms:
        if term in stop_terms:
            continue
        for product_term in product_suffixes:
            if term.endswith(product_term) and len(term) > len(product_term):
                brand_prefix = term[:-len(product_term)]
                if len(brand_prefix) >= 2 and brand_prefix not in stop_terms:
                    required.extend([product_term, brand_prefix, term])
                    break
    known_matches = []
    for term in sorted(known_specific_terms, key=len, reverse=True):
        if term in topic and not any(term in selected for selected in known_matches):
            known_matches.append(term)
    required.extend(known_matches)
    for term in raw_terms:
        if term in stop_terms:
            continue
        if len(term) >= 2 and len(term) <= 8:
            required.append(term)
    return [term for term in dict.fromkeys(required) if term not in stop_terms]


def extract_required_topic_groups(topic: str) -> Dict[str, List[str]]:
    topic = topic or ""
    required_terms = extract_required_topic_terms(topic)
    product_terms = []
    for term in sorted(KNOWN_PRODUCT_TERMS, key=len, reverse=True):
        if term in topic and not any(term in selected for selected in product_terms):
            product_terms.append(term)
    known_brand_terms = [term for term in KNOWN_BRAND_TERMS if term in topic]
    generic_non_brand = {
        "数据", "分析", "数据分析", "报告", "市场", "趋势", "行业", "美妆", "美业",
        "化妆品", "研究", "白皮书", "中国",
    }
    inferred_brand_terms = [
        term for term in required_terms
        if term not in product_terms
        and term not in generic_non_brand
        and not re.fullmatch(r"\d+", term)
        and not any(product_term in term for product_term in product_terms)
    ]
    groups = {
        "brand": [term for term in dict.fromkeys([*known_brand_terms, *inferred_brand_terms])],
        "product": product_terms,
    }
    return {key: value for key, value in groups.items() if value}


def calculate_match_details(reference: Dict[str, str], topic: str) -> Dict[str, Any]:
    content = " ".join(
        [
            reference.get("title", ""),
            reference.get("summary", ""),
            reference.get("content_text", ""),
            reference.get("url", ""),
        ]
    ).lower()
    terms = extract_topic_terms(topic)
    required_terms = extract_required_topic_terms(topic)
    required_groups = extract_required_topic_groups(topic)
    matched_terms = [term for term in terms if term in content]
    required_terms_matched = [term for term in required_terms if term.lower() in content]
    required_groups_matched = [
        group_name
        for group_name, group_terms in required_groups.items()
        if any(term.lower() in content for term in group_terms)
    ]
    # 关键词命中分：命中 required_terms 越多加分越高（非线性）
    req_hit_count = len(required_terms_matched)
    req_kw_score = _keyword_tier(req_hit_count) * 6   # 0/6/18/30
    # 一般 topic 词命中分（上限 40，避免泛词刷爆分）
    term_score = min(40, len(matched_terms) * 6) + req_kw_score
    term_score = min(term_score, 70)
    content_length = len(reference.get("content_text", "") or "")
    access_bonus = 20 if content_length >= 240 else 10 if content_length >= 80 else 0
    requested_bonus = 20 if is_user_requested_source(reference.get("publisher", "")) else 0
    url_path = urlparse(reference.get("url", "")).path.strip("/").lower()
    entry_paths = {"", "cn", "business", "about", "about-us", "index", "home"}
    is_entry_page = url_path in entry_paths or url_path.endswith("/about-us")
    # 产品页特征词：刻意只保留高精度信号，去掉 "products"/"services"/"solutions"
    # 等在普通新闻/分析文章的导航栏里也极常见的词，避免误判。
    # 对可信媒体域名（PREFERRED_PUBLISHERS）完全豁免此检查——它们几乎不是电商页。
    product_page_markers = (
        "add to cart", "add to bag", "加入购物车", "立即购买", "立即下单",
        "buy now", "shop now", "in stock", "out of stock",
        "marketing claims", "industry benchmarking", "pricing", "demo",
        "benchmark your company",
    )
    publisher_domain = reference.get("publisher", "") or extract_publisher(reference.get("url", ""))
    is_trusted_media = is_preferred_publisher(publisher_domain)
    is_product_page = (not is_trusted_media) and any(marker in content for marker in product_page_markers)
    # 数据文章评分（分层，复用 _data_article_score）
    data_score = _data_article_score(content)
    strong_data_signal = data_score >= 2 and not is_product_page
    # 分层加分：data_score 0→0, 1→10, 2→20, 3→28, 4→35
    data_signal_bonus = [0, 10, 20, 28, 35][min(data_score, 4)] if not is_product_page else 0
    entry_penalty = 35 if is_entry_page and not strong_data_signal else 15 if is_entry_page else 0
    product_penalty = 30 if is_product_page else 0
    match_score = max(0, min(100, term_score + access_bonus + requested_bonus + data_signal_bonus - entry_penalty - product_penalty))
    content_excerpt = reference.get("content_excerpt") or (reference.get("content_text", "") or "")[:360]
    access_status = "product_page" if is_product_page else "entry_page" if is_entry_page and not strong_data_signal else reference.get("access_status") or (
        "fetched" if content_length >= 20 and matched_terms else "thin_content"
    )

    return {
        "match_score": match_score,
        "matched_terms": matched_terms[:12],
        "required_terms": required_terms,
        "required_terms_matched": required_terms_matched,
        "required_groups_matched": required_groups_matched,
        "content_chars": content_length,
        "content_excerpt": clean_text(content_excerpt)[:360],
        "access_status": access_status,
        "data_signal": strong_data_signal,
    }


def score_reference(reference: Dict[str, str], topic: str = "") -> Tuple[int, int, int, int, int, str]:
    """最终资料排序打分（所有维度从高到低）：

    1. access_priority     — 内容可读性（fetched > thin_content > 其他）
    2. data_article_tier   — 数据文章优先级（0-4，命中数字+单位/报告/同比等）
    3. keyword_tier        — required_terms 命中数量分层（1中/2高/3+极高）
    4. required_group_hits — 命中的 required_groups 数
    5. relevance_bonus     — match_score（综合相关度）
    6. source_bonus        — 来源权威性（官方/机构/媒体 + 可信域名）
    7. published_at        — 时效（越新越优）
    """
    source_bonus = {"official": 3, "institution": 2, "media": 1}.get(
        reference.get("source_type", "media"), 0
    )
    publisher = reference.get("publisher", "")
    domain_bonus = 2 if is_preferred_publisher(publisher) else 0
    required_terms_matched = reference.get("required_terms_matched") or []
    keyword_hit = bool(required_terms_matched)
    requested_source_bonus = 4 if (keyword_hit and is_user_requested_source(publisher)) else 0
    text = " ".join(
        [
            reference.get("title", ""),
            reference.get("summary", ""),
            reference.get("content_excerpt", "") or "",
            reference.get("url", ""),
            reference.get("publisher", ""),
        ]
    ).lower()
    match_score = int(reference.get("match_score", 0) or 0)
    relevance_bonus = match_score or sum(1 for term in extract_topic_terms(topic) if term in text)
    access_priority = {
        "fetched": 3,
        "thin_content": 2,
        "product_page": 0,
        "entry_page": 0,
        "dynamic_required": 0,
        "login_required": 0,
        "paywalled": 0,
        "request_failed": 0,
    }.get(reference.get("access_status", ""), 1)
    # 数据文章优先级：命中摘要+正文里的数据信号
    data_article_tier = _data_article_score(text)
    # 关键词命中层级（命中1个/2个/3+个，分层加权）
    keyword_tier_priority = _keyword_tier(len(required_terms_matched))
    required_group_priority = len(reference.get("required_groups_matched") or [])
    published_at = reference.get("published_at") or "0000-00-00"
    return (
        access_priority,
        data_article_tier,
        keyword_tier_priority,
        required_group_priority,
        relevance_bonus,
        source_bonus + domain_bonus + requested_source_bonus,
        published_at,
    )


def _keyword_tier(hit_count: int) -> int:
    """关键词命中数 → 非线性优先级分层。
    命中越多，优先级指数级提升；0 命中不会被直接排除（由硬过滤兜底）。
    """
    if hit_count >= 3:
        return 5
    if hit_count == 2:
        return 3
    if hit_count == 1:
        return 1
    return 0


def _data_article_score(text: str) -> int:
    """判断文本是否含有数据型内容，返回 0-4 分层优先级。
    数字 + 单位 / 同比环比 / 报告白皮书 / 调研数据 均视为数据信号。
    """
    score = 0
    # 有数字+单位（市场规模、增速等）
    if re.search(r"\d+(?:\.\d+)?\s*(?:%|亿元|亿|万元|万|million|billion|增长|下降)", text):
        score += 2
    # 行业数据关键词
    data_kws = ("同比", "环比", "复合增长率", "cagr", "市场规模", "渗透率", "份额",
                 "销售额", "销量", "规模", "数据显示", "调查显示", "报告显示")
    if any(kw in text for kw in data_kws):
        score += 1
    # 文章类型：报告/白皮书/研究/洞察
    doc_kws = ("报告", "白皮书", "研究", "洞察", "调研", "分析报告", "行业报告", "market report")
    if any(kw in text for kw in doc_kws):
        score += 1
    return min(score, 4)


def score_candidate_for_enrichment(candidate: Dict[str, str], topic: str = "") -> Tuple[int, int, int, int, str]:
    """候选页面在 fetch 之前的排序打分（分越高越优先抓取）。

    排序维度（从高到低）：
    1. keyword_tier    — 命中 required_terms 的分层优先级
    2. data_score      — 标题/摘要含数据型内容
    3. group_hits      — 命中的 required_groups 数
    4. preferred_bonus — 可信媒体来源
    5. title           — 兜底字典序
    """
    text = " ".join(
        [
            candidate.get("title", ""),
            candidate.get("snippet", "") or candidate.get("summary", ""),
            candidate.get("url", ""),
            candidate.get("publisher", ""),
        ]
    ).lower()
    required_terms = extract_required_topic_terms(topic)
    required_hits = sum(1 for term in required_terms if term.lower() in text)
    required_groups = extract_required_topic_groups(topic)
    group_hits = sum(
        1 for terms in required_groups.values()
        if any(term.lower() in text for term in terms)
    )
    preferred_bonus = 1 if is_preferred_publisher(candidate.get("publisher", extract_publisher(candidate.get("url", "")))) else 0
    data_score = _data_article_score(text)
    keyword_tier = _keyword_tier(required_hits)
    return (keyword_tier, data_score, group_hits, preferred_bonus, candidate.get("title", ""))


def search_result_matches_required_topic(result: Dict[str, str], topic: str) -> bool:
    """硬过滤：搜索结果必须命中至少一个 required_term 才入候选池。

    匹配范围包含 title / url / snippet / summary / description —— 因为搜索引擎
    返回的原始 title 可能很短（如"青眼"），snippet 才能反映实际内容。
    """
    required_terms = extract_required_topic_terms(topic)
    if not required_terms:
        return True
    text = " ".join(
        [
            result.get("title", "") or "",
            result.get("url", "") or "",
            result.get("snippet", "") or "",
            result.get("summary", "") or "",
            result.get("description", "") or "",
        ]
    ).lower()
    if is_entertainment_content(text):
        return False
    return any(term.lower() in text for term in required_terms)


def seed_matches_required_topic(seed: Dict[str, Any], topic: str) -> bool:
    required_terms = extract_required_topic_terms(topic)
    if not required_terms:
        return True
    required_groups = extract_required_topic_groups(topic)
    category_terms = _broad_seed_category_terms(required_groups.get("product", []))
    text = " ".join(
        [
            seed.get("title", ""),
            seed.get("url", ""),
            seed.get("publisher", ""),
            " ".join(seed.get("keywords", ())),
        ]
    ).lower()
    if category_terms and any(term.lower() in text for term in category_terms):
        return True
    return any(term.lower() in text for term in required_terms)


def _reference_topic_bucket(reference: Dict[str, str], topic: str) -> int:
    required_groups = extract_required_topic_groups(topic)
    matched_groups = set(reference.get("required_groups_matched") or [])
    wants_brand = bool(required_groups.get("brand"))
    wants_product = bool(required_groups.get("product"))
    has_brand = "brand" in matched_groups
    has_product = "product" in matched_groups
    if wants_brand and wants_product:
        if has_brand and has_product:
            return 4
        if has_brand:
            return 3
        if has_product:
            return 1
        return 0
    if wants_brand:
        return 3 if has_brand else 0
    if wants_product:
        return 2 if has_product else 0
    return 0


def prefer_high_confidence_references(
    references: List[Dict[str, str]], limit: int, topic: str = ""
) -> List[Dict[str, str]]:
    required_groups = extract_required_topic_groups(topic)
    if required_groups.get("brand") and required_groups.get("product"):
        sorted_refs = sorted(
            references,
            key=lambda ref: (_reference_topic_bucket(ref, topic), score_reference(ref, topic)),
            reverse=True,
        )
        selected: List[Dict[str, str]] = []
        delayed_product_only: List[Dict[str, str]] = []
        product_only_limit = max(2, limit // 3)
        product_only_count = 0
        for ref in sorted_refs:
            bucket = _reference_topic_bucket(ref, topic)
            if bucket == 1 and product_only_count >= product_only_limit:
                delayed_product_only.append(ref)
                continue
            selected.append(ref)
            if bucket == 1:
                product_only_count += 1
            if len(selected) >= limit:
                return selected[:limit]
        for ref in delayed_product_only:
            selected.append(ref)
            if len(selected) >= limit:
                break
        return selected[:limit]

    preferred_refs = [
        ref for ref in references if is_preferred_publisher(ref.get("publisher", ""))
    ]
    if preferred_refs:
        preferred_sorted = sorted(preferred_refs, key=lambda ref: score_reference(ref, topic), reverse=True)
        if len(preferred_sorted) >= limit:
            return preferred_sorted[:limit]
        preferred_urls = {normalize_reference_url(ref.get("url", "")) for ref in preferred_sorted}
        fallback_refs = [
            ref
            for ref in references
            if normalize_reference_url(ref.get("url", "")) not in preferred_urls
        ]
        fallback_sorted = sorted(fallback_refs, key=lambda ref: score_reference(ref, topic), reverse=True)
        return (preferred_sorted + fallback_sorted)[:limit]
    return sorted(references, key=lambda ref: score_reference(ref, topic), reverse=True)[:limit]


def normalize_reference_url(url: str) -> str:
    parsed = urlparse(url or "")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def dedupe_references(references: List[Dict[str, str]]) -> List[Dict[str, str]]:
    deduped: List[Dict[str, str]] = []
    seen = set()
    for ref in references:
        excerpt_key = clean_text(ref.get("content_excerpt", ""))[:120]
        key = (normalize_reference_url(ref.get("url", "")), excerpt_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def build_snippet_reference(candidate: Dict[str, str], topic: str) -> Optional[Dict[str, str]]:
    summary = clean_text(candidate.get("snippet") or candidate.get("summary") or "")
    title = clean_text(candidate.get("title", ""))
    if not title and not summary:
        return None
    reference = {
        **candidate,
        "publisher": candidate.get("publisher") or extract_publisher(candidate.get("url", "")),
        "source_type": candidate.get("source_type") or infer_source_type(candidate.get("url", ""), title),
        "summary": summary,
        "content_text": f"{title} {summary}",
        "content_excerpt": summary or title,
        "access_status": "thin_content",
    }
    reference.update(calculate_match_details(reference, topic))
    if int(reference.get("match_score", 0) or 0) < MIN_USABLE_MATCH_SCORE:
        return None
    return reference


def filter_usable_references(
    references: List[Dict[str, str]],
    min_score: int = MIN_USABLE_MATCH_SCORE,
    required_terms: Optional[List[str]] = None,
    required_groups: Optional[Dict[str, List[str]]] = None,
    remembered_bad_sources: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    required_terms = required_terms or []
    required_groups = required_groups or {}
    usable = []
    rejected = []
    for ref in references:
        status = ref.get("access_status", "")
        score = int(ref.get("match_score", 0) or 0)
        publisher = ref.get("publisher", "") or extract_publisher(ref.get("url", ""))
        if is_remembered_bad_source(publisher, remembered_bad_sources) or is_remembered_bad_source(
            ref.get("url", ""),
            remembered_bad_sources,
        ):
            rejected.append({**ref, "reject_reason": "remembered_bad_source"})
            continue
        if is_entertainment_content(
            ref.get("title", ""),
            ref.get("summary", ""),
            ref.get("content_excerpt", ""),
            ref.get("content_text", ""),
            ref.get("url", ""),
            ref.get("publisher", ""),
        ):
            rejected.append({**ref, "reject_reason": "entertainment_content"})
            continue
        matched_required = ref.get("required_terms_matched") or [
            term for term in required_terms if term in (ref.get("matched_terms") or [])
        ]
        matched_groups = [
            group_name
            for group_name, terms in required_groups.items()
            if any(term in matched_required for term in terms)
        ]
        is_category_context = (
            required_groups
            and not matched_required
            and status in USABLE_ACCESS_STATUSES
            and score >= 20
            and is_preferred_publisher(publisher)
            and bool(ref.get("data_signal") or _data_article_score(" ".join([
                ref.get("title", ""),
                ref.get("summary", ""),
                ref.get("content_excerpt", ""),
            ])))
        )
        effective_min_score = MIN_REQUIRED_TERM_MATCH_SCORE if matched_required else min_score
        if status not in USABLE_ACCESS_STATUSES:
            rejected.append({**ref, "reject_reason": f"unusable_status_{status or 'unknown'}"})
        elif is_category_context:
            usable.append({**ref, "required_groups_matched": ["category_context"]})
        elif required_terms and not matched_required:
            rejected.append({**ref, "reject_reason": "missing_required_terms"})
        elif score < effective_min_score:
            rejected.append({**ref, "reject_reason": f"match_score_below_{effective_min_score}"})
        elif required_groups and not matched_groups:
            rejected.append({**ref, "reject_reason": "missing_required_groups"})
        else:
            usable.append({**ref, "required_groups_matched": matched_groups})
    return usable, rejected


def _extract_json_array(raw: str) -> List[Dict[str, Any]]:
    clean = (raw or "").strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
    start = clean.find("[")
    end = clean.rfind("]") + 1
    if start < 0 or end <= start:
        raise ValueError("AI 资料评审未返回 JSON 数组")
    payload = json.loads(re.sub(r",\s*([}\]])", r"\1", clean[start:end]))
    if not isinstance(payload, list):
        raise ValueError("AI 资料评审 JSON 顶层不是数组")
    return [item for item in payload if isinstance(item, dict)]


def _compact_reference_for_ai(ref: Dict[str, str]) -> Dict[str, Any]:
    excerpt = clean_text(
        ref.get("content_excerpt")
        or ref.get("summary")
        or ref.get("content_text", "")[:500]
        or ""
    )
    return {
        "title": clean_text(ref.get("title", ""))[:120],
        "url": ref.get("url", ""),
        "publisher": ref.get("publisher") or extract_publisher(ref.get("url", "")),
        "source_type": ref.get("source_type", "media"),
        "published_at": ref.get("published_at") or "",
        "access_status": ref.get("access_status") or "",
        "python_match_score": int(ref.get("match_score", 0) or 0),
        "required_terms_matched": ref.get("required_terms_matched") or [],
        "required_groups_matched": ref.get("required_groups_matched") or [],
        "excerpt": excerpt[:700],
    }


def _call_ai_reference_judge(
    topic: str,
    candidates: List[Dict[str, str]],
    limit: int,
    timeout: int = 45,
) -> List[Dict[str, Any]]:
    system = (
        "你是美妆行业白皮书资料主编。只输出 JSON 数组，不要解释。"
        "你的任务是从候选资料里挑出最适合写白皮书的资料，严格排除无关行业、食品饮料、音乐娱乐、"
        "纯产品页、入口页、百科问答、种草排行和没有数据价值的内容。"
    )
    compact = [_compact_reference_for_ai(ref) for ref in candidates]
    prompt = f"""
用户报告主题：{topic}
目标：最多选出 {limit} 条可用于白皮书正文学习的资料。

评分规则：
1. relevance_score: 0-100，是否匹配用户主题、品牌、产品、品类。食品饮料等非美妆相关必须低分。
2. data_score: 0-100，是否包含市场规模、增速、销售、趋势、报告、调研、财报等数据价值。
3. authority_score: 0-100，官方、机构报告、权威媒体、核心产业媒体优先。
4. usable: true/false，只有适合白皮书引用和学习的资料才 true。
5. reason: 用一句中文说明入选或淘汰原因。

重要约束：
- 即使来源是白名单权威机构，只要页面主题不属于美妆/护肤/彩妆/香氛/化妆品/消费零售相关，也必须 usable=false。
- 用户输入含品牌和产品时，品牌页、品类页、行业报告都可以入选，但纯购物/教程/排行/问答不要入选。
- 不要因为 Python 的 python_match_score 高就照单全收，你要重新判断。

候选资料 JSON：
{json.dumps(compact, ensure_ascii=False)}

请返回 JSON 数组，每项格式：
{{
  "url": "候选资料原 URL",
  "usable": true,
  "relevance_score": 0,
  "data_score": 0,
  "authority_score": 0,
  "reason": "一句中文原因"
}}
"""
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _extract_json_array(content)


def ai_select_references(
    references: List[Dict[str, str]],
    topic: str,
    limit: int,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """用 AI 做最终资料主编筛选；AI 不可用时回退到旧规则排序。"""
    if not references:
        return [], []
    if not RESEARCH_AI_RERANK_ENABLED or not DEEPSEEK_API_KEY:
        return prefer_high_confidence_references(references, limit, topic), []

    candidates = sorted(references, key=lambda ref: score_reference(ref, topic), reverse=True)[
        :RESEARCH_AI_RERANK_CANDIDATES
    ]
    try:
        judgements = _call_ai_reference_judge(topic, candidates, limit)
    except Exception as exc:
        print(f"[Research][AISelect] AI资料评审失败，回退规则排序: {exc}")
        return prefer_high_confidence_references(references, limit, topic), []

    by_url = {normalize_reference_url(ref.get("url", "")): ref for ref in candidates}
    selected: List[Dict[str, str]] = []
    rejected: List[Dict[str, str]] = []
    seen = set()
    for item in judgements:
        normalized_url = normalize_reference_url(str(item.get("url", "")))
        ref = by_url.get(normalized_url)
        if not ref or normalized_url in seen:
            continue
        seen.add(normalized_url)
        ai_relevance = _safe_int(item.get("relevance_score"), 0) or 0
        ai_data = _safe_int(item.get("data_score"), 0) or 0
        ai_authority = _safe_int(item.get("authority_score"), 0) or 0
        annotated = {
            **ref,
            "ai_relevance_score": ai_relevance,
            "ai_data_score": ai_data,
            "ai_authority_score": ai_authority,
            "ai_reason": clean_text(str(item.get("reason", "")))[:180],
        }
        if item.get("usable") is True and ai_relevance >= 45:
            annotated["ai_overall_score"] = ai_relevance * 3 + ai_data * 2 + ai_authority
            selected.append(annotated)
        else:
            rejected.append({**annotated, "reject_reason": "ai_rejected"})

    if not seen:
        print("[Research][AISelect] AI资料评审未匹配任何 URL，回退规则排序")
        return prefer_high_confidence_references(references, limit, topic), []

    selected.sort(
        key=lambda ref: (
            int(ref.get("ai_overall_score", 0) or 0),
            score_reference(ref, topic),
        ),
        reverse=True,
    )
    print(f"[Research][AISelect] 入选 {min(len(selected), limit)} 条 / AI淘汰 {len(rejected)} 条")
    for idx, ref in enumerate(selected[:limit], 1):
        print(
            "[Research][AISelect] "
            f"入选 {idx}: ai={ref.get('ai_relevance_score')}/{ref.get('ai_data_score')}/{ref.get('ai_authority_score')} "
            f"source={ref.get('publisher')} title={ref.get('title')}"
        )
    for ref in rejected[:8]:
        print(
            "[Research][AISelect] 淘汰: "
            f"reason={ref.get('ai_reason')} source={ref.get('publisher')} title={ref.get('title')}"
        )
    if not selected:
        fallback = _fallback_ai_rejected_context(candidates, topic, limit=min(3, limit))
        if fallback:
            print(f"[Research][AISelect] AI全淘汰，保留 {len(fallback)} 条低置信背景资料")
            selected = fallback
    return selected[:limit], rejected


def _fallback_ai_rejected_context(
    references: List[Dict[str, str]],
    topic: str,
    limit: int = 3,
) -> List[Dict[str, str]]:
    blocked_publishers = {
        "suning.com",
        "taobao.com",
        "tmall.com",
        "jd.com",
        "mall.jd.com",
        "m.baike.com",
        "baike.com",
        "baike.baidu.com",
        "jingyan.baidu.com",
        "zhidao.baidu.com",
    }
    allowed_status = {"fetched", "thin_content"}
    candidates = []
    for ref in references:
        publisher = ref.get("publisher", "") or extract_publisher(ref.get("url", ""))
        status = ref.get("access_status", "")
        if publisher in blocked_publishers or status not in allowed_status:
            continue
        if is_entertainment_content(
            ref.get("title", ""),
            ref.get("summary", ""),
            ref.get("content_excerpt", ""),
            ref.get("url", ""),
            publisher,
        ):
            continue
        if is_allowed_result_url(ref.get("url", "")) is False:
            continue
        matched_required = ref.get("required_terms_matched") or []
        if not matched_required and int(ref.get("match_score", 0) or 0) < 50:
            continue
        candidates.append(
            {
                **ref,
                "ai_fallback": True,
                "ai_reason": "AI严格评审未选出资料，作为低置信背景资料保留；正文应谨慎使用。",
                "ai_relevance_score": max(1, int(ref.get("match_score", 0) or 0)),
                "ai_data_score": 0,
                "ai_authority_score": 50 if ref.get("source_type") in {"official", "institution"} else 30,
            }
        )
    candidates.sort(key=lambda ref: score_reference(ref, topic), reverse=True)
    return candidates[:limit]


def collect_recent_references_debug(
    topic: str, limit: int = 10, timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    def make_session() -> requests.Session:
        local_session = requests.Session()
        local_session.headers.update({"User-Agent": "Mozilla/5.0"})
        return local_session

    session = make_session()
    search_request_limit = min(MAX_SEARCH_REQUESTS, RESEARCH_MAX_SEARCH_REQUESTS)
    fetch_page_limit = min(MAX_CANDIDATES_TO_ENRICH, RESEARCH_MAX_FETCH_PAGES)
    target_reference_limit = min(limit, RESEARCH_TARGET_REFERENCES)
    budget = {
        "mode": RESEARCH_BUDGET_MODE,
        "search_request_limit": search_request_limit,
        "fetch_page_limit": fetch_page_limit,
        "target_references": target_reference_limit,
        "scrapfly_cost_budget_search": SCRAPFLY_COST_BUDGET_SEARCH,
        "scrapfly_cost_budget_page": SCRAPFLY_COST_BUDGET_PAGE,
        "scrapfly_cache_ttl": SCRAPFLY_CACHE_TTL,
        "cache_hit": False,
    }
    effective_search_workers = min(
        RESEARCH_SEARCH_WORKERS,
        SCRAPFLY_SEARCH_CONCURRENCY if SCRAPFLY_API_KEY else RESEARCH_SEARCH_WORKERS,
        max(1, search_request_limit),
    )
    budget["search_workers"] = effective_search_workers
    use_cache = timeout >= 5
    cached_payload = _load_research_cache(topic) if use_cache else None
    if cached_payload:
        budget["cache_hit"] = True
        cached_budget = dict(cached_payload.get("budget") or {})
        cached_budget.update(budget)
        return {
            **cached_payload,
            "budget": cached_budget,
            "search_logs": cached_payload.get("search_logs", []),
            "fetch_logs": cached_payload.get("fetch_logs", []),
        }
    if SCRAPFLY_API_KEY:
        print(f"[Research] 使用 Scrapfly 云爬虫代理（key=****{SCRAPFLY_API_KEY[-4:]}）")
    else:
        print("[Research] 未配置 SCRAPFLY_API_KEY，使用本机直连（可能被反爬拦截）")
    research_lessons = _load_research_lessons(topic)
    remembered_bad_sources = _load_research_bad_sources(topic)
    if research_lessons:
        print(f"[Research][Memory]\n{research_lessons}")
    if remembered_bad_sources:
        print(f"[Research][Memory] remembered_bad_sources={', '.join(remembered_bad_sources)}")
    print(
        "[Research][Budget] "
        f"mode={budget['mode']} search_limit={search_request_limit} "
        f"fetch_limit={fetch_page_limit} target_refs={target_reference_limit} "
        f"cache_ttl={SCRAPFLY_CACHE_TTL}"
    )

    candidates: Dict[str, Dict[str, str]] = {}
    search_logs: List[Dict[str, Any]] = []
    fetch_logs: List[Dict[str, Any]] = []
    required_terms_for_candidates = extract_required_topic_terms(topic)
    for seed in REQUESTED_REFERENCE_SEEDS:
        if is_allowed_result_url(seed.get("url", "")) and (
            not required_terms_for_candidates
            or seed_matches_required_topic(seed, topic)
        ):
            candidates[seed["url"]] = seed

    with ThreadPoolExecutor(max_workers=MAX_RESEARCH_WORKERS) as pool:
        futures = [
            pool.submit(discover_source_candidates, seed, make_session(), timeout, topic)
            for seed in REQUESTED_REFERENCE_SEEDS
            if is_allowed_result_url(seed.get("url", ""))
        ]
        for future in as_completed(futures):
            for discovered in future.result():
                candidates.setdefault(discovered["url"], discovered)

    for seed in get_curated_reference_seeds(topic):
        if is_allowed_result_url(seed.get("url", "")):
            candidates[seed["url"]] = seed

    search_sources = [
        ("duckduckgo", search_duckduckgo),
        ("baidu", search_baidu),
        ("bing", search_bing),
        ("so360", search_so360),
    ]

    def _add_result_to_candidates(result: dict, source_name: str) -> None:
        url = result.get("url", "")
        if not url or url in candidates:
            return
        publisher = extract_publisher(url)
        if is_remembered_bad_source(publisher, remembered_bad_sources) or is_remembered_bad_source(
            url,
            remembered_bad_sources,
        ):
            return
        if not search_result_matches_required_topic(result, topic):
            return
        if not is_allowed_result_url(url):
            return
        candidates[url] = {
            "title": result.get("title", "").strip(),
            "url": url,
            "source_type": infer_source_type(url, result.get("title", "")),
            "publisher": extract_publisher(url),
            "published_at": None,
            "summary": result.get("snippet", ""),
            "snippet": result.get("snippet", ""),
            "search_source": source_name,
        }

    search_jobs = []
    for query in build_search_queries(topic)[:MAX_SEARCH_QUERIES]:
        for source_name, search_fn in search_sources:
            if len(search_jobs) >= search_request_limit:
                break
            search_jobs.append((source_name, search_fn, query))
        if len(search_jobs) >= search_request_limit:
            break

    def _run_search_job(job: Tuple[str, Any, str]) -> Tuple[str, str, List[Dict[str, str]], str]:
        source_name, search_fn, query = job
        try:
            return source_name, query, search_fn(query, make_session(), timeout)[:10], ""
        except Exception as exc:
            return source_name, query, [], str(exc)[:160]

    for batch_start in range(0, len(search_jobs), effective_search_workers):
        batch_jobs = search_jobs[batch_start:batch_start + effective_search_workers]
        with ThreadPoolExecutor(max_workers=max(1, len(batch_jobs))) as pool:
            future_to_job = {pool.submit(_run_search_job, job): job for job in batch_jobs}
            for future in as_completed(future_to_job):
                source_name, query, results, error = future.result()
                log_item = {"source": source_name, "query": query, "result_count": len(results)}
                if error:
                    log_item["error"] = error
                search_logs.append(log_item)
                for result in results:
                    _add_result_to_candidates(result, source_name)

    candidate_values = sorted(
        candidates.values(),
        key=lambda candidate: score_candidate_for_enrichment(candidate, topic),
        reverse=True,
    )[:fetch_page_limit]

    required_terms = extract_required_topic_terms(topic)
    required_groups = extract_required_topic_groups(topic)
    enriched: List[Dict[str, str]] = []
    rejected: List[Dict[str, str]] = []
    usable: List[Dict[str, str]] = []
    final_results: List[Dict[str, str]] = []
    for batch_start in range(0, len(candidate_values), RESEARCH_FETCH_BATCH_SIZE):
        batch = candidate_values[batch_start:batch_start + RESEARCH_FETCH_BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=min(MAX_RESEARCH_WORKERS, max(1, len(batch)))) as pool:
            futures = [
                pool.submit(enrich_reference, candidate, make_session(), timeout)
                for candidate in batch
            ]
            for future in as_completed(futures):
                enriched_candidate = future.result()
                if enriched_candidate:
                    enriched_candidate.update(calculate_match_details(enriched_candidate, topic))
                    fetch_logs.append(
                        {
                            "url": enriched_candidate.get("url"),
                            "title": enriched_candidate.get("title"),
                            "publisher": enriched_candidate.get("publisher"),
                            "status": enriched_candidate.get("access_status"),
                            "score": enriched_candidate.get("match_score"),
                            "required_terms_matched": enriched_candidate.get("required_terms_matched"),
                            "required_groups_matched": enriched_candidate.get("required_groups_matched"),
                            "scrapfly_cost": enriched_candidate.get("scrapfly_cost", 0),
                            "scrapfly_cache_state": enriched_candidate.get("scrapfly_cache_state", ""),
                            "scrapfly_remaining_credit": enriched_candidate.get("scrapfly_remaining_credit"),
                        }
                    )
                    enriched.append(enriched_candidate)

        enriched = [
            ref for ref in enriched
            if ref.get("match_score", 0) >= 20
            or (ref.get("required_terms_matched") and is_user_requested_source(ref.get("publisher", "")))
        ]
        enriched.sort(key=lambda ref: score_reference(ref, topic), reverse=True)
        enriched = dedupe_references(enriched)
        usable, rejected = filter_usable_references(
            enriched,
            required_terms=required_terms,
            required_groups=required_groups,
            remembered_bad_sources=remembered_bad_sources,
        )
        final_results = prefer_high_confidence_references(usable, target_reference_limit, topic)
        high_quality_hits = [
            ref for ref in final_results
            if int(ref.get("match_score", 0) or 0) >= RESEARCH_EARLY_STOP_MIN_SCORE
        ]
        if (
            len(final_results) >= max(target_reference_limit, RESEARCH_EARLY_STOP_MIN_RESULTS)
            and len(high_quality_hits) >= max(target_reference_limit, RESEARCH_EARLY_STOP_MIN_RESULTS)
        ):
            print(
                "[Research][EarlyStop] "
                f"batch_end={batch_start + len(batch)} high_quality={len(high_quality_hits)} "
                f"target={target_reference_limit}"
            )
            break

    if len(final_results) < target_reference_limit:
        enriched_urls = {normalize_reference_url(ref.get("url", "")) for ref in enriched}
        snippet_refs = []
        for candidate in candidate_values:
            if normalize_reference_url(candidate.get("url", "")) in enriched_urls:
                continue
            snippet_ref = build_snippet_reference(candidate, topic)
            if snippet_ref:
                snippet_refs.append(snippet_ref)
        if snippet_refs:
            enriched.extend(snippet_refs)
            enriched.sort(key=lambda ref: score_reference(ref, topic), reverse=True)
            enriched = dedupe_references(enriched)
            usable, rejected = filter_usable_references(
                enriched,
                required_terms=required_terms,
                required_groups=required_groups,
                remembered_bad_sources=remembered_bad_sources,
            )
            final_results = prefer_high_confidence_references(usable, target_reference_limit, topic)

    final_results, ai_rejected = ai_select_references(usable, topic, target_reference_limit)
    if ai_rejected:
        rejected.extend(ai_rejected)

    low_quality_selected = [
        ref.get("publisher", "")
        for ref in final_results
        if ref.get("publisher") in {"image.so.com", "wenda.so.com", "wenku.so.com", "docin.com"}
    ]
    memory_failures = [
        ref.get("publisher", "") for ref in rejected if ref.get("reject_reason") == "entertainment_content"
    ]
    if len(final_results) < target_reference_limit or low_quality_selected or memory_failures:
        _record_research_failure(
            "entertainment_content" if memory_failures else "low_quality_selection" if low_quality_selected else "insufficient_references",
            topic,
            memory_failures or low_quality_selected or [ref.get("publisher", "") for ref in rejected[:8]],
        )
    observed_fetch_cost = sum(int(log.get("scrapfly_cost") or 0) for log in fetch_logs)
    budget["observed_fetch_cost"] = observed_fetch_cost
    payload = {
        "final_results": final_results,
        "rejected_results": rejected,
        "candidates": list(candidates.values()),
        "candidate_count": len(candidates),
        "enriched_count": len(enriched),
        "usable_count": len(usable),
        "min_match_score": MIN_USABLE_MATCH_SCORE,
        "usable_statuses": list(USABLE_ACCESS_STATUSES),
        "required_terms": required_terms,
        "required_groups": required_groups,
        "search_logs": search_logs,
        "fetch_logs": fetch_logs,
        "budget": budget,
    }
    if final_results and use_cache:
        _save_research_cache(topic, payload)
    return payload


def collect_recent_references(topic: str, limit: int = 10, timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, str]]:
    return collect_recent_references_debug(topic, limit=limit, timeout=timeout)["final_results"]


def build_research_context(references: List[Dict[str, str]]) -> str:
    if not references:
        return ""

    lines = [
        "以下内容只作为事实背景供正文吸收，不要在正文逐条列出来源名称、链接或清单；外部来源信息由系统在正文之后统一追加。",
    ]
    for idx, ref in enumerate(references, 1):
        date_text = ref.get("published_at") or "日期未提取"
        summary = ref.get("summary", "").strip()
        lines.append(
            f"{idx}. {ref.get('title', '')} | 匹配度: {ref.get('match_score', 0)}/100 | 来源类型: {ref.get('source_type', '')} | 发布方: {ref.get('publisher', '')} | 日期: {date_text}"
        )
        matched_terms = ref.get("matched_terms") or []
        if matched_terms:
            lines.append(f"   匹配词: {', '.join(matched_terms)}")
        if summary:
            lines.append(f"   摘要: {summary[:220]}")
        excerpt = ref.get("content_excerpt", "").strip()
        if excerpt:
            lines.append(f"   可读正文摘录: {excerpt[:260]}")
        lines.append(f"   抓取状态: {ref.get('access_status', 'unknown')}")
    return "\n".join(lines)
