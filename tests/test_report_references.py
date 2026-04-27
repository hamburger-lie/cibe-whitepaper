import json

import proxy


class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, system: str) -> str:
        self.calls.append({"prompt": prompt, "system": system})

        if system == proxy.AGENT1_SYSTEM:
            return json.dumps(
                {
                    "whitepaper_meta": {
                        "title": "测试白皮书",
                        "subtitle": "副标题",
                        "global_tone": "专业",
                        "target_audience": "决策层",
                    },
                    "front_matter": {
                        "executive_summary": {
                            "executive_judgement": "核心判断",
                            "key_findings": ["发现一"],
                            "core_data_points": ["数据点一"],
                        },
                        "research_note": {
                            "research_object": "研究对象",
                            "time_scope": "2024-2026",
                            "data_sources": ["官方公告", "机构报告"],
                            "sample_scope": "样本口径",
                            "method_boundary": "研究边界",
                            "term_definition": "名词定义",
                        },
                    },
                    "chapters": [
                        {
                            "chapter_id": "01",
                            "chapter_title": "判断句标题",
                            "core_proposition": "核心问题",
                            "chapter_intro": "导语",
                            "sub_sections": [
                                {
                                    "section_id": "01-1",
                                    "section_title": "小节标题",
                                    "section_focus": "焦点",
                                }
                            ],
                            "data_anchors": ["数据锚点"],
                            "case_direction": "案例方向",
                            "content_guidelines": "正文要求",
                            "transition_from_previous": "承接",
                            "needs_chart": False,
                            "chart_intent": "none",
                            "visual_type": "none",
                            "image_intent": "none",
                            "chapter_summary": "章节总结",
                        }
                    ],
                    "back_matter": {
                        "conclusion_summary": {
                            "final_judgement": "总结判断",
                            "industry_implications": ["启示一"],
                        },
                        "action_recommendations": {
                            "for_brands": ["建议一"],
                            "for_channels": ["建议二"],
                            "for_investment_or_strategy": ["建议三"],
                        },
                        "risk_and_boundary_notes": ["风险一"],
                        "references_or_appendix": {
                            "required": True,
                            "content_direction": "参考数据来源说明",
                        },
                    },
                },
                ensure_ascii=False,
            )

        if system == proxy.AGENT2_SYSTEM:
            if '[IMAGE_PLACEHOLDER id="01"]' in prompt:
                return '## 一、判断句标题\n\n正文内容。\n\n[IMAGE_PLACEHOLDER id="01"]'
            return "## 一、判断句标题\n\n正文内容。"

        if system == proxy.AGENT4_SYSTEM:
            return json.dumps(
                {"type": "bar", "title": "图表", "labels": [], "datasets": []},
                ensure_ascii=False,
            )

        if system == proxy.AGENT3_SYSTEM:
            return "高端美妆产品陈列真实摄影，洁净实验室台面，浅景深，精准布光，电影级色调"

        return "unused"


class FakeImageGenerator:
    available = True


def test_pipeline_includes_research_context_and_reference_links(monkeypatch):
    fake_llm = FakeLLM()
    monkeypatch.setattr(proxy, "get_llm_provider", lambda: fake_llm)
    monkeypatch.setattr(proxy, "ENABLE_REFLECTION", False)

    references = [
        {
            "title": "L'Oreal 2025 Annual Report",
            "url": "https://example.com/loreal-2025",
            "source_type": "official",
            "publisher": "L'Oreal",
            "published_at": "2025-02-06",
            "summary": "Contains recent premium beauty performance data.",
            "match_score": 88,
            "matched_terms": ["粉底", "美妆", "市场"],
            "access_status": "fetched",
        },
        {
            "title": "NPD Beauty Trends 2024",
            "url": "https://example.com/npd-2024",
            "source_type": "institution",
            "publisher": "Circana",
            "published_at": "2024-11-01",
            "summary": "Tracks prestige beauty market trends.",
        },
    ]

    markdown = proxy.run_four_agent_pipeline(
        "高端粉底市场分析",
        research_context="已检索到近两年官方与机构资料，可优先引用。",
        references=references,
    )

    assert "## 参考资料与链接" in markdown
    assert "https://example.com/loreal-2025" in markdown
    assert "https://example.com/npd-2024" in markdown
    assert "匹配度：88/100" not in markdown
    assert "抓取状态：fetched" not in markdown

    chapter_prompts = [
        call["prompt"] for call in fake_llm.calls if call["system"] == proxy.AGENT2_SYSTEM
    ]
    assert chapter_prompts
    assert "已检索到近两年官方与机构资料" in chapter_prompts[0]


def test_research_context_does_not_feed_reference_links_into_body():
    context = proxy.build_research_context(
        [
            {
                "title": "谷雨品牌面膜数据报告",
                "url": "https://example.com/report",
                "publisher": "example.com",
                "source_type": "media",
                "published_at": "2026-01-01",
                "summary": "面膜市场规模增长。",
                "match_score": 80,
                "matched_terms": ["谷雨", "面膜"],
                "content_excerpt": "报告显示，面膜市场规模同比增长。",
                "access_status": "fetched",
            }
        ]
    )

    assert "https://example.com/report" not in context
    assert "参考资料" not in context
    assert "文末" not in context
    assert "只作为事实背景" in context


def test_strategy_prompt_requires_at_least_three_image_intents():
    assert "至少 3 章" in proxy.AGENT1_SYSTEM
    assert "禁止所有章节 image_intent 都为 none" in proxy.AGENT1_SYSTEM
    assert '"image_intent": "必须写具体可拍摄场景；全文至少3章如此填写' in proxy.AGENT1_USER


def test_pipeline_runs_reflection_after_reference_links_are_appended(monkeypatch):
    fake_llm = FakeLLM()
    seen = {}

    monkeypatch.setattr(proxy, "get_llm_provider", lambda: fake_llm)
    monkeypatch.setattr(proxy, "ENABLE_REFLECTION", True)

    def fake_reflection(markdown, original_data):
        seen["markdown"] = markdown
        return markdown + "\n\n## 反思与验证\n\n来源一致性已检查。"

    monkeypatch.setattr(proxy, "_apply_reflection_and_verification_sync", fake_reflection)

    references = [
        {
            "title": "L'Oreal 2025 Annual Report",
            "url": "https://example.com/loreal-2025",
            "source_type": "official",
            "publisher": "loreal-finance.com",
            "published_at": "2025-02-06",
            "summary": "Contains recent premium beauty performance data.",
        },
    ]

    markdown = proxy.run_four_agent_pipeline(
        "高端粉底市场分析",
        research_context="已检索到来源。",
        references=references,
    )

    assert "## 参考资料与链接" in seen["markdown"]
    assert "https://example.com/loreal-2025" in seen["markdown"]
    assert "来源一致性已检查" in markdown


def test_pipeline_generates_fallback_image_prompt_when_outline_has_no_image_intent(monkeypatch):
    fake_llm = FakeLLM()
    monkeypatch.setattr(proxy, "get_llm_provider", lambda: fake_llm)
    monkeypatch.setattr(proxy, "ENABLE_REFLECTION", False)
    monkeypatch.setattr(proxy, "image_generator", FakeImageGenerator())
    monkeypatch.setattr(proxy, "IMAGE_PROMPT_CACHE_TTL", 0)

    markdown = proxy.run_four_agent_pipeline("TF眼影市场分析")

    assert '<image prompt="' in markdown
    assert any(call["system"] == proxy.AGENT3_SYSTEM for call in fake_llm.calls)
