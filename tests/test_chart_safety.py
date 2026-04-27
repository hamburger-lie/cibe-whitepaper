from proxy import _normalize_chart_config
from proxy import _parse_llm_json
from proxy import _load_pipeline_lessons
from proxy import _record_pipeline_failure
from proxy import _sanitize_placeholder_numbers
from proxy import _should_skip_reflection_fast_path
from proxy import _image_prompt_cache_key
from proxy import _load_image_prompt_cache
from proxy import _save_image_prompt_cache
from web_access_research import _load_research_lessons
from web_access_research import _load_research_bad_sources
from web_access_research import _record_research_failure
import web_access_research
import proxy


def test_normalize_chart_config_rejects_empty_or_malformed_data():
    assert _normalize_chart_config(None) is None
    assert _normalize_chart_config({"type": "bar", "labels": [], "datasets": []}) is None
    assert _normalize_chart_config({"labels": ["A", "B"], "datasets": [{"name": "x"}]}) is None


def test_normalize_chart_config_pads_values_and_sanitizes_type():
    normalized = _normalize_chart_config(
        {
            "type": "bad-type",
            "title": "超长标题" * 20,
            "labels": ["A", "B", "C"],
            "datasets": [{"name": "销售", "values": [12, "bad"]}],
        }
    )

    assert normalized["type"] == "bar"
    assert normalized["title"]
    assert normalized["labels"] == ["A", "B", "C"]
    assert normalized["datasets"] == [{"name": "销售", "values": [12.0, 0.0, 0.0]}]


def test_parse_llm_json_repairs_truncated_nested_outline():
    raw = """
    {
      "whitepaper_meta": {"title": "修复精华赛道", "target_audience": "品牌方"},
      "chapters": [
        {"chapter_id": "01", "chapter_title": "功效验证", "sub_sections": [
          {"section_id": "01-1", "section_title": "屏障修复"}
        ]}
      ],
      "back_matter": {"risk_and_boundary_notes": ["样本有限"]
    """

    parsed = _parse_llm_json(raw)

    assert parsed["whitepaper_meta"]["title"] == "修复精华赛道"
    assert parsed["chapters"][0]["sub_sections"][0]["section_title"] == "屏障修复"


def test_pipeline_failure_memory_records_and_loads_lessons(tmp_path, monkeypatch):
    memory_path = tmp_path / "pipeline_memory.json"
    monkeypatch.setattr(proxy, "PIPELINE_MEMORY_PATH", str(memory_path))

    _record_pipeline_failure("outline_json", ValueError("无法解析 LLM 返回的 JSON"), '{"bad":')
    lessons = _load_pipeline_lessons()

    assert "outline_json" in lessons
    assert "完整合法 JSON" in lessons


def test_research_failure_memory_records_low_quality_selection(tmp_path, monkeypatch):
    memory_path = tmp_path / "research_memory.json"
    monkeypatch.setattr(web_access_research, "RESEARCH_MEMORY_PATH", str(memory_path))

    _record_research_failure(
        "low_quality_selection",
        "谷雨面膜",
        ["image.so.com", "wenda.so.com"],
    )
    lessons = _load_research_lessons("谷雨面膜")

    assert "谷雨面膜" in lessons
    assert "image.so.com" in lessons
    assert "低质量" in lessons


def test_research_failure_memory_loads_bad_sources_for_related_topic(tmp_path, monkeypatch):
    memory_path = tmp_path / "research_memory.json"
    monkeypatch.setattr(web_access_research, "RESEARCH_MEMORY_PATH", str(memory_path))

    _record_research_failure(
        "entertainment_content",
        "雅诗兰黛眼霜",
        ["music.163.com", "y.qq.com"],
    )
    bad_sources = _load_research_bad_sources("雅诗兰黛 眼霜 雅诗兰黛眼霜")

    assert "music.163.com" in bad_sources
    assert "y.qq.com" in bad_sources


class KeywordLLM:
    def generate(self, prompt: str, system: str) -> str:
        assert system == proxy.KEYWORD_EXTRACT_SYSTEM
        return '{"brand_terms":["雅诗兰黛"],"product_terms":["眼霜"],"compound_terms":["雅诗兰黛眼霜"]}'


def test_extract_research_topic_with_ai_uses_brand_product_and_compound(monkeypatch):
    monkeypatch.setattr(proxy, "get_llm_provider", lambda: KeywordLLM())

    topic = proxy._extract_research_topic_with_ai("【文字输入】\n雅诗兰黛眼霜")

    assert topic == "雅诗兰黛 眼霜 雅诗兰黛眼霜"


def test_sanitize_placeholder_numbers_removes_x_placeholders():
    markdown = "2025年中国眼霜市场规模预计突破XXX亿元，同比增长XX%，客单价至X元。"

    cleaned = _sanitize_placeholder_numbers(markdown)

    assert "XXX" not in cleaned
    assert "XX%" not in cleaned
    assert "X元" not in cleaned
    assert "公开资料未披露具体数值" in cleaned


def test_should_skip_reflection_for_high_confidence_whitepaper():
    markdown = "\n".join(
        [
            "## 执行摘要",
            "A" * 2500,
            "## 研究说明",
            "B" * 2200,
            "## 一、市场全景",
            "C" * 2200,
            "## 二、竞争格局",
            "D" * 2200,
        ]
    )
    references = [{"title": f"ref-{i}"} for i in range(8)]

    assert _should_skip_reflection_fast_path(markdown, references) is True


def test_should_not_skip_reflection_for_short_or_sparse_whitepaper():
    assert _should_skip_reflection_fast_path("太短", [{"title": "only-one"}]) is False


def test_image_prompt_cache_round_trips_prompt(tmp_path, monkeypatch):
    cache_path = tmp_path / "image_prompt_cache.json"
    monkeypatch.setattr(proxy, "IMAGE_PROMPT_CACHE_PATH", str(cache_path))
    monkeypatch.setattr(proxy, "IMAGE_PROMPT_CACHE_TTL", 604800)
    cache_key = _image_prompt_cache_key("门店陈列", "高端护肤", "渠道体验升级")

    _save_image_prompt_cache(cache_key, "高端护肤门店陈列，真实摄影")

    assert _load_image_prompt_cache(cache_key) == "高端护肤门店陈列，真实摄影"
