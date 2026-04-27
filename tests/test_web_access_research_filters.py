from web_access_research import (
    BaiduResultParser,
    MAX_CANDIDATES_TO_ENRICH,
    MAX_DISCOVERED_LINKS_PER_SOURCE,
    MAX_SEARCH_REQUESTS,
    MAX_SEARCH_QUERIES,
    clean_text,
    collect_recent_references,
    build_search_queries,
    calculate_match_details,
    classify_access_status,
    collect_recent_references_debug,
    discover_links_from_html,
    discover_source_candidates,
    extract_pdf_text,
    dedupe_references,
    get_curated_reference_seeds,
    infer_source_type,
    is_allowed_result_url,
    is_preferred_publisher,
    is_relevant_source_link,
    is_user_requested_source,
    normalize_search_result_url,
    prefer_high_confidence_references,
    filter_usable_references,
    extract_required_topic_terms,
    extract_required_topic_groups,
    search_result_matches_required_topic,
    seed_matches_required_topic,
    score_reference,
    score_candidate_for_enrichment,
)
import web_access_research as research


def test_is_allowed_result_url_blocks_known_low_quality_domains():
    assert not is_allowed_result_url("https://www.sohu.com/a/123")
    assert not is_allowed_result_url("https://www.qyresearch.com.cn/reports/1")
    assert not is_allowed_result_url("https://max.book118.com/html/2025/test")
    assert not is_allowed_result_url("https://beaut.taobao.com/topic/saihong.html")
    assert not is_allowed_result_url("https://www.cnpp.cn/china/paihang_264.html")
    assert not is_allowed_result_url("https://image.so.com/i?q=%E8%B0%B7%E9%9B%A8%E9%9D%A2%E8%86%9C")
    assert not is_allowed_result_url("https://wenda.so.com/q/1679291222213003")
    assert not is_allowed_result_url("https://wenku.so.com/d/abc")
    assert not is_allowed_result_url("https://www.docin.com/p-4583897150.html")
    assert not is_allowed_result_url("https://www.zhihu.com/tardis/bd/art/694797836")
    assert not is_allowed_result_url("https://post.smzdm.com/p/an58d5wp/")
    assert not is_allowed_result_url("https://baike.so.com/doc/3095746-3263069.html")
    assert not is_allowed_result_url("https://jingyan.baidu.com/article/b7001fe1d00f394f7282ddea.html")
    assert not is_allowed_result_url("https://hk.cosme.net/ranking/846")
    assert not is_allowed_result_url("https://www.360kuai.com/pc/925751c3b9754fb6c")
    assert not is_allowed_result_url("https://tv.360kan.com/player?id=123")
    assert not is_allowed_result_url("http://m.360video.so.com/link/example")
    assert not is_allowed_result_url("https://map.360.cn/?q=%E9%A6%99%E5%A5%88%E5%84%BF")
    assert not is_allowed_result_url("https://www.baidu.com/link?url=ad")
    assert not is_allowed_result_url("https://zhidao.baidu.com/question/123.html")
    assert not is_allowed_result_url("https://news.so.com/ns?q=%E9%A6%99%E5%A5%88%E5%84%BF")
    assert not is_allowed_result_url("https://music.163.com/song?id=123456")
    assert not is_allowed_result_url("https://y.qq.com/n/ryqq/songDetail/001")
    assert is_allowed_result_url("https://www.reuters.com/world/china/beauty-market-2025/")
    assert is_allowed_result_url("https://news.qq.com/rain/a/20251120A048DG00")
    assert is_allowed_result_url("https://finance.sina.cn/2026-01-21/detail.html")
    assert is_preferred_publisher("news.qq.com")


def test_prefer_high_confidence_references_prioritizes_whitelist_then_fills_limit():
    references = [
        {
            "title": "KPMG Beauty Report",
            "url": "https://assets.kpmg.com/report.pdf",
            "publisher": "assets.kpmg.com",
            "source_type": "institution",
            "published_at": "2025-11-14",
            "summary": "trusted",
        },
        {
            "title": "Random repost",
            "url": "https://random-example.net/article/abc.html",
            "publisher": "random-example.net",
            "source_type": "media",
            "published_at": "2026-04-15",
            "summary": "noisy",
        },
    ]

    filtered = prefer_high_confidence_references(references, limit=10)

    assert filtered[0]["publisher"] == "assets.kpmg.com"
    assert len(filtered) == 2


def test_filter_usable_references_requires_fetched_and_score_at_least_50():
    references = [
        {"title": "可用资料", "access_status": "fetched", "match_score": 55},
        {"title": "低分资料", "access_status": "fetched", "match_score": 40},
        {"title": "产品页", "access_status": "product_page", "match_score": 95},
        {"title": "付费页", "access_status": "paywalled", "match_score": 100},
    ]

    usable, rejected = filter_usable_references(references, min_score=50)

    assert [ref["title"] for ref in usable] == ["可用资料"]
    assert {ref["title"]: ref["reject_reason"] for ref in rejected} == {
        "低分资料": "match_score_below_50",
        "产品页": "unusable_status_product_page",
        "付费页": "unusable_status_paywalled",
    }


def test_search_result_matches_required_topic_rejects_song_like_results():
    result = {
        "title": "雅诗兰黛主题曲 - QQ音乐",
        "url": "https://y.qq.com/n/ryqq/songDetail/001",
        "snippet": "在线试听歌词MV播放",
    }

    assert not search_result_matches_required_topic(result, "雅诗兰黛 眼霜 雅诗兰黛眼霜")


def test_filter_usable_references_rejects_entertainment_content_even_with_keyword_match():
    references = [
        {
            "title": "雅诗兰黛主题曲 - 网易云音乐",
            "url": "https://music.163.com/song?id=123456",
            "publisher": "music.163.com",
            "access_status": "fetched",
            "match_score": 80,
            "matched_terms": ["雅诗兰黛"],
            "required_terms_matched": ["雅诗兰黛"],
        }
    ]

    usable, rejected = filter_usable_references(
        references,
        min_score=50,
        required_terms=["雅诗兰黛", "眼霜"],
    )

    assert not usable
    assert rejected[0]["reject_reason"] == "entertainment_content"


def test_filter_usable_references_allows_preferred_category_context_reports():
    references = [
        {
            "title": "KPMG China Consumer & Retail Industry Analysis",
            "url": "https://kpmg.com/cn/report",
            "publisher": "kpmg.com",
            "access_status": "fetched",
            "match_score": 25,
            "matched_terms": [],
            "required_terms_matched": [],
            "data_signal": True,
            "summary": "美妆 护肤 市场规模 数据 报告显示增长12%。",
        }
    ]

    usable, rejected = filter_usable_references(
        references,
        required_terms=["花西子", "散粉"],
        required_groups={"brand": ["花西子"], "product": ["散粉"]},
    )

    assert rejected == []
    assert usable[0]["required_groups_matched"] == ["category_context"]


def test_collect_recent_references_uses_memory_to_skip_bad_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(research, "RESEARCH_MEMORY_PATH", str(tmp_path / "research_memory.json"))
    research._record_research_failure(
        "entertainment_content",
        "雅诗兰黛眼霜",
        ["music.163.com"],
    )
    monkeypatch.setattr(research, "REQUESTED_REFERENCE_SEEDS", [])
    monkeypatch.setattr(research, "get_curated_reference_seeds", lambda topic: [])
    monkeypatch.setattr(research, "build_search_queries", lambda topic: ['"雅诗兰黛" 眼霜'])

    def fake_search(query, session, timeout):
        return [
            {
                "title": "雅诗兰黛主题曲 - 网易云音乐",
                "url": "https://music.163.com/song?id=123456",
                "snippet": "歌词播放",
            },
            {
                "title": "雅诗兰黛眼霜行业报告",
                "url": "https://example.com/report",
                "snippet": "雅诗兰黛 眼霜 市场数据",
            },
        ]

    monkeypatch.setattr(research, "search_duckduckgo", fake_search)
    monkeypatch.setattr(research, "search_baidu", lambda *args, **kwargs: [])
    monkeypatch.setattr(research, "search_bing", lambda *args, **kwargs: [])
    monkeypatch.setattr(research, "search_so360", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        research,
        "enrich_reference",
        lambda candidate, session, timeout: {
            **candidate,
            "publisher": research.extract_publisher(candidate["url"]),
            "source_type": "media",
            "published_at": "2026-04-24",
            "summary": candidate.get("snippet", ""),
            "content_text": "雅诗兰黛眼霜市场规模增长，报告显示高端护肤持续扩容。",
            "content_excerpt": "雅诗兰黛眼霜市场规模增长，报告显示高端护肤持续扩容。",
            "access_status": "fetched",
            "match_score": 80,
        },
    )

    payload = collect_recent_references_debug("雅诗兰黛 眼霜 雅诗兰黛眼霜", limit=5, timeout=10)

    assert all(ref["publisher"] != "music.163.com" for ref in payload["final_results"])
    assert any(ref["publisher"] == "example.com" for ref in payload["final_results"])


def test_memory_bad_sources_ignores_insufficient_reference_domains(monkeypatch, tmp_path):
    monkeypatch.setattr(research, "RESEARCH_MEMORY_PATH", str(tmp_path / "research_memory.json"))
    research._record_research_failure(
        "insufficient_references",
        "香奈儿 香水 香奈儿香水",
        ["chanel.cn", "163.com"],
    )

    assert research._load_research_bad_sources("香奈儿 香水 香奈儿香水") == []


def test_memory_bad_sources_does_not_blacklist_preferred_publishers(monkeypatch, tmp_path):
    monkeypatch.setattr(research, "RESEARCH_MEMORY_PATH", str(tmp_path / "research_memory.json"))
    research._record_research_failure(
        "entertainment_content",
        "花西子 散粉 花西子散粉",
        ["loreal-finance.com", "music.163.com"],
    )

    assert research._load_research_bad_sources("花西子 散粉 花西子散粉") == ["music.163.com"]


def test_collect_recent_references_debug_uses_cache_before_search(monkeypatch, tmp_path):
    monkeypatch.setattr(research, "RESEARCH_CACHE_PATH", str(tmp_path / "research_cache.json"))
    monkeypatch.setattr(research, "RESEARCH_CACHE_TTL", 86400)
    research._save_research_cache(
        "雅诗兰黛 眼霜 雅诗兰黛眼霜",
        {
            "final_results": [
                {
                    "title": "缓存命中资料",
                    "url": "https://example.com/cache-report",
                    "publisher": "example.com",
                    "source_type": "media",
                    "published_at": "2026-04-24",
                    "summary": "缓存摘要",
                    "content_excerpt": "缓存正文",
                    "access_status": "fetched",
                    "match_score": 88,
                }
            ],
            "rejected_results": [],
            "candidates": [],
            "candidate_count": 1,
            "enriched_count": 1,
            "usable_count": 1,
        },
    )
    monkeypatch.setattr(research, "search_duckduckgo", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("search should not run")))
    monkeypatch.setattr(research, "search_baidu", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("search should not run")))
    monkeypatch.setattr(research, "search_bing", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("search should not run")))
    monkeypatch.setattr(research, "search_so360", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("search should not run")))

    payload = collect_recent_references_debug("雅诗兰黛 眼霜 雅诗兰黛眼霜", limit=5, timeout=10)

    assert payload["final_results"][0]["title"] == "缓存命中资料"
    assert payload["budget"]["cache_hit"] is True


def test_extract_required_topic_terms_keeps_brand_and_specific_product_terms():
    required = extract_required_topic_terms("彩棠粉饼 数据分析")

    assert "彩棠" in required
    assert "粉饼" in required
    assert "数据分析" not in required


def test_extract_required_topic_terms_splits_unknown_brand_and_compound_product():
    required = extract_required_topic_terms("自然堂修复精华")

    assert required[:3] == ["修复精华", "自然堂", "自然堂修复精华"]


def test_extract_required_topic_terms_splits_mask_brand_and_product():
    required = extract_required_topic_terms("谷雨面膜")

    assert required[:3] == ["面膜", "谷雨", "谷雨面膜"]


def test_extract_required_topic_terms_splits_eye_cream_brand_and_product():
    required = extract_required_topic_terms("雅诗兰黛眼霜")

    assert required[:3] == ["眼霜", "雅诗兰黛", "雅诗兰黛眼霜"]


def test_extract_required_topic_terms_splits_face_cream_and_perfume_products():
    assert "面霜" in extract_required_topic_terms("大宝面霜")
    assert "香水" in extract_required_topic_terms("香奈儿香水")


def test_build_search_queries_adds_category_report_queries_for_brand_product():
    queries = build_search_queries("花西子 散粉 花西子散粉")

    assert any("彩妆" in query and "报告" in query for query in queries[:16])
    assert any("site:36kr.com" in query for query in queries)


def test_build_search_queries_prioritizes_combined_data_queries_before_standalone_terms():
    queries = build_search_queries("香奈儿 香水 香奈儿香水")

    assert queries[:4] == [
        '"香奈儿" 香水 香奈儿香水',
        '"香奈儿" 香水 香奈儿香水 市场',
        '"香奈儿" 香水 香奈儿香水 数据',
        '"香奈儿" 香水 香奈儿香水 报告',
    ]


def test_seed_matches_required_topic_allows_broad_beauty_reports_for_product_topic():
    seed = {
        "title": "McKinsey State of Beauty 2025",
        "url": "https://www.mckinsey.com/industries/consumer-packaged-goods/our-insights/state-of-beauty",
        "publisher": "mckinsey.com",
        "keywords": ("美妆", "护肤", "beauty", "consumer"),
    }

    assert seed_matches_required_topic(seed, "自然堂 修复精华 自然堂修复精华")


def test_extract_required_topic_groups_splits_brand_and_product_terms():
    groups = extract_required_topic_groups("彩棠粉饼 数据分析")

    assert groups == {"brand": ["彩棠"], "product": ["粉饼"]}


def test_extract_required_topic_groups_treats_unknown_non_generic_term_as_brand():
    groups = extract_required_topic_groups("花知晓 腮红")

    assert groups == {"brand": ["花知晓"], "product": ["腮红"]}


def test_extract_required_topic_groups_splits_unknown_brand_from_product_phrase():
    groups = extract_required_topic_groups("自然堂修复精华")

    assert groups == {"brand": ["自然堂"], "product": ["修复精华"]}


def test_extract_required_topic_groups_splits_mask_brand_from_product_phrase():
    groups = extract_required_topic_groups("谷雨面膜")

    assert groups == {"brand": ["谷雨"], "product": ["面膜"]}


def test_extract_required_topic_groups_splits_eye_cream_brand_from_product_phrase():
    groups = extract_required_topic_groups("雅诗兰黛眼霜")

    assert groups == {"brand": ["雅诗兰黛"], "product": ["眼霜"]}


def test_filter_usable_references_requires_brand_or_specific_product_match():
    references = [
        {
            "title": "泛美妆市场报告",
            "access_status": "fetched",
            "match_score": 80,
            "matched_terms": ["美妆", "市场", "趋势"],
        },
        {
            "title": "彩棠粉饼资料",
            "access_status": "fetched",
            "match_score": 55,
            "matched_terms": ["彩棠", "粉饼", "底妆"],
        },
    ]

    usable, rejected = filter_usable_references(
        references,
        min_score=50,
        required_terms=["彩棠", "粉饼"],
    )

    assert [ref["title"] for ref in usable] == ["彩棠粉饼资料"]
    assert rejected[0]["reject_reason"] == "missing_required_terms"


def test_filter_usable_references_lowers_score_floor_when_required_term_matches():
    references = [
        {
            "title": "花知晓资料整理",
            "access_status": "fetched",
            "match_score": 28,
            "matched_terms": ["花知晓"],
            "required_terms_matched": ["花知晓"],
        },
        {
            "title": "腮红行业报告",
            "access_status": "fetched",
            "match_score": 43,
            "matched_terms": ["腮红"],
            "required_terms_matched": ["腮红"],
        },
        {
            "title": "泛美妆低分资料",
            "access_status": "fetched",
            "match_score": 28,
            "matched_terms": ["美妆"],
            "required_terms_matched": [],
        },
    ]

    usable, rejected = filter_usable_references(
        references,
        min_score=50,
        required_terms=["花知晓", "腮红"],
    )

    assert [ref["title"] for ref in usable] == ["花知晓资料整理", "腮红行业报告"]
    assert rejected[0]["reject_reason"] == "missing_required_terms"


def test_filter_usable_references_requires_brand_and_product_groups():
    references = [
        {
            "title": "只命中粉饼",
            "access_status": "fetched",
            "match_score": 80,
            "matched_terms": ["粉饼", "底妆"],
            "required_terms_matched": ["粉饼"],
        },
        {
            "title": "彩棠粉饼资料",
            "access_status": "fetched",
            "match_score": 55,
            "matched_terms": ["彩棠", "粉饼"],
            "required_terms_matched": ["彩棠", "粉饼"],
        },
    ]

    usable, rejected = filter_usable_references(
        references,
        min_score=50,
        required_terms=["彩棠", "粉饼"],
        required_groups={"brand": ["彩棠"], "product": ["粉饼"]},
    )

    assert [ref["title"] for ref in usable] == ["只命中粉饼", "彩棠粉饼资料"]
    assert not rejected


def test_score_reference_prioritizes_references_matching_brand_and_product():
    partial = {
        "title": "粉饼品类资料",
        "access_status": "fetched",
        "match_score": 70,
        "required_groups_matched": ["product"],
        "published_at": "2025-01-01",
    }
    complete = {
        "title": "彩棠粉饼资料",
        "access_status": "fetched",
        "match_score": 70,
        "required_groups_matched": ["brand", "product"],
        "published_at": "2025-01-01",
    }

    assert score_reference(complete, "彩棠粉饼") > score_reference(partial, "彩棠粉饼")


def test_prefer_high_confidence_references_limits_product_only_when_brand_is_requested():
    references = [
        {
            "title": "粉底液数据报告",
            "url": "https://reportify.cn/foundation-report",
            "publisher": "reportify.cn",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 90,
            "required_terms_matched": ["粉底液"],
            "required_groups_matched": ["product"],
            "content_excerpt": "粉底液市场规模100亿元，同比增长9%，报告显示趋势增长。",
            "published_at": "2026-01-01",
        },
        {
            "title": "花西子品牌分析",
            "url": "https://www.cbndata.com/brand/huaxizi",
            "publisher": "cbndata.com",
            "source_type": "institution",
            "access_status": "fetched",
            "match_score": 70,
            "required_terms_matched": ["花西子"],
            "required_groups_matched": ["brand"],
            "content_excerpt": "花西子品牌市场数据报告，销售额100亿元，同比增长9%。",
            "published_at": "2025-01-01",
        },
        {
            "title": "花西子粉底液研究",
            "url": "https://www.datastory.com.cn/huaxizi-foundation",
            "publisher": "datastory.com.cn",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 80,
            "required_terms_matched": ["花西子", "粉底液"],
            "required_groups_matched": ["brand", "product"],
            "content_excerpt": "花西子粉底液市场研究报告，销售额100亿元，同比增长9%。",
            "published_at": "2025-06-01",
        },
        {
            "title": "粉底液排行种草",
            "url": "https://www.zhihu.com/question/foundation-rank",
            "publisher": "zhihu.com",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 85,
            "required_terms_matched": ["粉底液"],
            "required_groups_matched": ["product"],
            "content_excerpt": "好用粉底液排行和使用体验。",
            "published_at": "2026-04-01",
        },
    ]

    selected = prefer_high_confidence_references(references, limit=4, topic="花西子 粉底液")

    assert [ref["title"] for ref in selected[:2]] == ["花西子粉底液研究", "花西子品牌分析"]
    assert selected[-1]["title"] == "粉底液排行种草"


def test_prefer_high_confidence_references_keeps_brand_before_preferred_product_only():
    references = [
        {
            "title": "Vogue 粉底液趋势报告",
            "url": "https://www.vogue.com.cn/foundation-trend",
            "publisher": "vogue.com.cn",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 92,
            "required_terms_matched": ["粉底液"],
            "required_groups_matched": ["product"],
            "content_excerpt": "粉底液市场规模100亿元，同比增长9%，报告显示趋势增长。",
            "published_at": "2026-01-01",
        },
        {
            "title": "花西子品牌市场报告",
            "url": "https://example.com/huaxizi-brand-report",
            "publisher": "example.com",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 65,
            "required_terms_matched": ["花西子"],
            "required_groups_matched": ["brand"],
            "content_excerpt": "花西子品牌市场报告，销售额100亿元，同比增长9%。",
            "published_at": "2025-01-01",
        },
    ]

    selected = prefer_high_confidence_references(references, limit=2, topic="花西子 粉底液")

    assert [ref["title"] for ref in selected] == ["花西子品牌市场报告", "Vogue 粉底液趋势报告"]


def test_preferred_publisher_requires_real_domain_boundary():
    assert is_preferred_publisher("assets.ey.com")
    assert not is_preferred_publisher("data.eastmoney.com")
    assert infer_source_type("https://data.eastmoney.com/report/example", "美妆行业报告") == "media"
    assert is_preferred_publisher("china.mintel.com")
    assert is_preferred_publisher("trendinsight.oceanengine.com")
    assert is_preferred_publisher("nmpa.gov.cn")
    assert is_user_requested_source("trendinsight.oceanengine.com")
    assert not is_user_requested_source("loreal-finance.com")


def test_build_search_queries_targets_user_requested_sources():
    queries = build_search_queries("高端粉底市场趋势")
    joined = "\n".join(queries)

    assert '"粉底"' in joined
    assert "美妆 彩妆 护肤 趋势" not in joined
    assert len(queries) <= MAX_SEARCH_QUERIES


def test_build_search_queries_starts_with_exact_required_terms():
    queries = build_search_queries("花知晓 腮红")

    assert queries[:4] == ['"花知晓" 腮红', '"花知晓" 腮红 市场', '"花知晓" 腮红 数据', '"花知晓" 腮红 报告']
    assert '"花知晓"' in queries
    assert '"腮红"' in queries
    joined = "\n".join(queries)
    assert "美妆 彩妆 护肤 趋势" not in joined
    assert "中国 美妆 市场 报告 2025" not in joined
    assert "高端 彩妆 市场 趋势 2025" not in joined


def test_build_search_queries_interleaves_brand_and_product_before_budget_cutoff():
    queries = build_search_queries("花西子 散粉")
    early_queries = queries[:8]

    assert '"花西子" 散粉' in early_queries
    assert any("花西子" in query and "散粉" in query for query in queries[:12])
    assert any("彩妆" in query or "底妆" in query for query in queries[:16])
    assert any("花西子" in query and "散粉" in query for query in early_queries[:4])
    assert any(query.startswith('"散粉"') for query in queries)


def test_build_search_queries_expands_brand_alias_and_category_for_eye_cream():
    queries = build_search_queries("雅诗兰黛 眼霜 雅诗兰黛眼霜")
    joined = "\n".join(queries[:16])

    assert '"雅诗兰黛" 眼霜 雅诗兰黛眼霜' in queries[:4]
    assert "雅诗兰黛集团" in joined
    assert "Estee Lauder" in joined or "Estée Lauder" in joined
    assert "眼部护理" in joined
    assert "site:elcompanies.com" in joined


def test_score_candidate_for_enrichment_prioritizes_exact_terms_over_big_sites():
    relevant_news = {
        "title": "花知晓腮红品牌分析",
        "url": "https://www.36kr.com/p/example",
        "publisher": "36kr.com",
    }
    generic_big_site = {
        "title": "中国美妆市场报告",
        "url": "https://www.euromonitor.com/report",
        "publisher": "euromonitor.com",
    }

    assert score_candidate_for_enrichment(relevant_news, "花知晓 腮红") > score_candidate_for_enrichment(generic_big_site, "花知晓 腮红")


def test_search_limits_are_expanded_for_baidu_and_larger_candidate_pool():
    assert MAX_SEARCH_QUERIES == 24
    assert MAX_SEARCH_REQUESTS == 96
    assert MAX_CANDIDATES_TO_ENRICH == 80
    assert MAX_DISCOVERED_LINKS_PER_SOURCE == 10


def test_baidu_result_parser_extracts_result_links():
    html = '''
    <html><body>
      <a href="https://www.baidu.com/link?url=abc123">2025 美妆市场报告</a>
      <a href="https://example.com/direct-report">高端粉底趋势</a>
    </body></html>
    '''
    parser = BaiduResultParser()
    parser.feed(html)

    assert parser.results == [
        {"title": "高端粉底趋势", "url": "https://example.com/direct-report"},
    ]


def test_normalize_search_result_url_decodes_bing_redirects():
    url = "https://www.bing.com/ck/a?u=a1aHR0cHM6Ly93d3cuMzZrci5jb20vcC85OTQ1OTEzMzE0OTgxMTY"

    assert normalize_search_result_url(url) == "https://www.36kr.com/p/994591331498116"


def test_search_result_matches_required_topic_allows_single_required_term():
    assert search_result_matches_required_topic(
        {"title": "花知晓品牌分析", "url": "https://example.com/a"},
        "花知晓 腮红",
    )
    assert search_result_matches_required_topic(
        {"title": "腮红行业报告", "url": "https://example.com/a"},
        "花知晓 腮红",
    )
    assert not search_result_matches_required_topic(
        {"title": "Microsoft account", "url": "https://example.com/a"},
        "花知晓 腮红",
    )


def test_seed_matches_required_topic_can_use_seed_keywords():
    assert seed_matches_required_topic(
        {
            "title": "英敏特 Mintel 中国洞察",
            "url": "https://china.mintel.com/",
            "publisher": "china.mintel.com",
            "keywords": ("美妆", "粉底", "底妆"),
        },
        "高端粉底市场趋势",
    )
    assert seed_matches_required_topic(
        {
            "title": "英敏特 Mintel 中国洞察",
            "url": "https://china.mintel.com/",
            "publisher": "china.mintel.com",
            "keywords": ("美妆", "粉底", "底妆"),
        },
        "卡姿兰 散粉 品牌分析",
    )


def test_relevant_source_link_requires_user_terms_for_specific_topics():
    assert not is_relevant_source_link(
        "香氛洗衣液暴涨43%，木质香增速75%",
        "https://hometest.mktindex.com/research/notebook/article_20260416",
        "卡姿兰 散粉 品牌分析",
    )
    assert is_relevant_source_link(
        "卡姿兰散粉品牌分析",
        "https://example.com/report",
        "卡姿兰 散粉 品牌分析",
    )


def test_discover_links_from_html_finds_relevant_same_site_reports():
    html = """
    <html><body>
      <a href="/reports/beauty-foundation-2025">2025 美妆粉底趋势报告</a>
      <a href="https://spam.example.com/report">转载报告</a>
      <a href="/about">关于我们</a>
    </body></html>
    """

    links = discover_links_from_html(
        html,
        "https://china.mintel.com/",
        "china.mintel.com",
        "高端粉底市场趋势",
    )

    assert links == [
        {
            "title": "2025 美妆粉底趋势报告",
            "url": "https://china.mintel.com/reports/beauty-foundation-2025",
        }
    ]


def test_discover_source_candidates_adds_inside_source_pages():
    class FakeResponse:
        status_code = 200
        text = '<a href="/insights/beauty-foundation-2025">2025 中国美妆粉底市场洞察报告</a>'

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    seed = {
        "title": "英敏特 Mintel 中国洞察",
        "url": "https://china.mintel.com/",
        "source_type": "institution",
        "publisher": "china.mintel.com",
    }

    candidates = discover_source_candidates(seed, FakeSession(), 1, "中国高端粉底市场趋势")

    assert candidates[0]["url"] == "https://china.mintel.com/insights/beauty-foundation-2025"
    assert candidates[0]["publisher"] == "china.mintel.com"
    assert candidates[0]["source_type"] == "institution"


def test_score_reference_rewards_topic_relevance():
    relevant = {
        "title": "2025 高端粉底与美妆市场趋势报告",
        "url": "https://china.mintel.com/beauty-report",
        "publisher": "china.mintel.com",
        "source_type": "institution",
        "published_at": "2025-05-01",
        "summary": "覆盖中国美妆、底妆、彩妆消费趋势。",
    }
    generic = {
        "title": "企业新闻",
        "url": "https://china.mintel.com/company-news",
        "publisher": "china.mintel.com",
        "source_type": "institution",
        "published_at": "2025-05-01",
        "summary": "公司动态。",
    }

    assert score_reference(relevant, "高端粉底市场趋势") > score_reference(generic, "高端粉底市场趋势")


def test_calculate_match_details_uses_fetched_content():
    reference = {
        "title": "普通入口页",
        "url": "https://china.mintel.com/beauty-foundation-report",
        "publisher": "china.mintel.com",
        "summary": "",
        "content_text": "中国高端粉底和底妆市场增长，消费者关注彩妆功效、护肤成分与线上渠道趋势。",
    }

    details = calculate_match_details(reference, "高端粉底市场趋势")

    assert details["match_score"] >= 50
    assert "粉底" in details["matched_terms"]
    assert details["access_status"] == "fetched"
    assert "高端粉底" in details["content_excerpt"]


def test_calculate_match_details_demotes_entry_pages_without_data():
    reference = {
        "title": "Vogue Business",
        "url": "https://www.vogue.com/business",
        "publisher": "vogue.com",
        "summary": "Fashion industry expertise.",
        "content_text": "Beauty makeup foundation market trend insight fashion industry business account menu.",
    }

    details = calculate_match_details(reference, "高端粉底市场趋势")

    assert details["access_status"] == "entry_page"
    assert details["match_score"] < 70


def test_calculate_match_details_demotes_vendor_product_pages():
    reference = {
        "title": "Marketing Claims",
        "url": "https://www.euromonitor.com/marketing-claims",
        "publisher": "euromonitor.com",
        "summary": "Strengthen your brand credibility with marketing claims.",
        "content_text": "Marketing Claims strengthen your brand credibility with beauty market insight from 5000 experts.",
    }

    details = calculate_match_details(reference, "高端粉底市场趋势")

    assert details["access_status"] == "fetched"
    assert details["data_signal"] is False


def test_classify_access_status_detects_paywall_login_and_dynamic_pages():
    assert classify_access_status("请登录后查看完整报告", 1000) == "fetched"
    assert classify_access_status("请登录后查看完整报告", 20) == "login_required"
    assert classify_access_status("订阅会员后下载完整报告", 1000) == "fetched"
    assert classify_access_status("订阅后阅读全文", 20) == "paywalled"
    assert classify_access_status("<div id='app'></div><script>window.__NUXT__={}</script>", 20) == "dynamic_required"
    assert classify_access_status("公开报告正文，销售额100亿元，同比增长9%。", 200) == "fetched"


def test_extract_pdf_text_returns_empty_for_invalid_pdf_bytes():
    assert extract_pdf_text(b"%PDF invalid") == ""


def test_dedupe_references_removes_same_url_and_excerpt_duplicates():
    references = [
        {
            "title": "魔镜洞察",
            "url": "https://hometest.mktindex.com/research/notebook/article_20260304",
            "content_excerpt": "2025年度美妆护肤线上市场趋势洞察",
            "match_score": 100,
        },
        {
            "title": "¶",
            "url": "https://hometest.mktindex.com/research/notebook/article_20260304/",
            "content_excerpt": "2025年度美妆护肤线上市场趋势洞察",
            "match_score": 100,
        },
    ]

    deduped = dedupe_references(references)

    assert len(deduped) == 1
    assert deduped[0]["title"] == "魔镜洞察"


def test_score_reference_prioritizes_user_requested_sources():
    requested_source = {
        "title": "美妆市场趋势报告",
        "url": "https://www.iqingyan.cn/report",
        "publisher": "iqingyan.cn",
        "source_type": "media",
        "published_at": "2025-01-01",
        "summary": "中国美妆行业趋势。",
        "required_terms_matched": ["美妆"],
    }
    brand_source = {
        "title": "美妆市场趋势报告",
        "url": "https://www.loreal-finance.com/report",
        "publisher": "loreal-finance.com",
        "source_type": "official",
        "published_at": "2025-01-01",
        "summary": "中国美妆行业趋势。",
        "required_terms_matched": ["美妆"],
    }

    assert score_reference(requested_source, "美妆市场趋势") > score_reference(brand_source, "美妆市场趋势")


def test_score_reference_prioritizes_free_fetched_content_over_paywalled_pages():
    free_reference = {
        "title": "美妆市场趋势报告",
        "url": "https://www.iqingyan.cn/report",
        "publisher": "iqingyan.cn",
        "source_type": "media",
        "published_at": "2025-01-01",
        "summary": "中国美妆行业趋势。",
        "match_score": 82,
        "access_status": "fetched",
    }
    paywalled_reference = {
        "title": "美妆市场趋势报告",
        "url": "https://m.cbndata.com/report",
        "publisher": "m.cbndata.com",
        "source_type": "institution",
        "published_at": "2026-01-01",
        "summary": "中国美妆行业趋势。",
        "match_score": 100,
        "access_status": "paywalled",
    }

    assert score_reference(free_reference, "美妆市场趋势") > score_reference(paywalled_reference, "美妆市场趋势")


def test_score_reference_prioritizes_data_signal_pages_over_product_pages():
    data_reference = {
        "title": "2025 美妆市场趋势洞察",
        "url": "https://hometest.mktindex.com/research/notebook/article_20260304",
        "publisher": "mktindex.com",
        "source_type": "institution",
        "published_at": "2025-01-01",
        "summary": "销售额4541.8亿元，同比增长9.7%。",
        "match_score": 90,
        "access_status": "fetched",
        "data_signal": True,
    }
    product_reference = {
        "title": "Marketing Claims",
        "url": "https://www.euromonitor.com/marketing-claims",
        "publisher": "euromonitor.com",
        "source_type": "institution",
        "published_at": "2026-01-01",
        "summary": "Beauty market trend insight report.",
        "match_score": 100,
        "access_status": "fetched",
        "data_signal": False,
    }

    assert score_reference(data_reference, "美妆市场趋势") > score_reference(product_reference, "美妆市场趋势")


def test_get_curated_reference_seeds_matches_beauty_topics():
    seeds = get_curated_reference_seeds("高端粉底市场趋势")

    assert len(seeds) >= 10
    assert any("loreal-finance.com" in seed["publisher"] for seed in seeds)
    assert any("circana.com" in seed["publisher"] or "kpmg.com" in seed["publisher"] for seed in seeds)
    assert any("mckinsey.com" in seed["publisher"] for seed in seeds)
    assert any("elcompanies.com" in seed["publisher"] for seed in seeds)


def test_get_curated_reference_seeds_matches_estee_lauder_eye_cream():
    seeds = get_curated_reference_seeds("雅诗兰黛 眼霜 雅诗兰黛眼霜")

    assert any(seed["publisher"] == "elcompanies.com" for seed in seeds)


def test_clean_text_repairs_common_mojibake_sequences():
    dirty = "Explore the 2024 Annual Report from LâOrÃ©al"
    cleaned = clean_text(dirty)

    assert "L’Oréal" in cleaned or "L'Oréal" in cleaned


def test_collect_recent_references_uses_curated_sources_to_reach_limit(monkeypatch):
    monkeypatch.setattr("web_access_research.search_duckduckgo", lambda *args, **kwargs: [])
    monkeypatch.setattr("web_access_research.search_baidu", lambda *args, **kwargs: [])
    monkeypatch.setattr("web_access_research.search_bing", lambda *args, **kwargs: [])
    monkeypatch.setattr("web_access_research.search_so360", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "web_access_research.enrich_reference",
        lambda candidate, session, timeout: {
            **candidate,
            "published_at": candidate.get("published_at") or "2025-01-01",
            "summary": candidate.get("summary") or candidate.get("title", ""),
            "content_text": "中国美妆高端粉底彩妆市场趋势报告，销售额100亿元，同比增长9%，覆盖消费者、渠道、护肤和底妆数据。",
            "content_excerpt": "中国美妆高端粉底彩妆市场趋势报告，销售额100亿元，同比增长9%，覆盖消费者、渠道、护肤和底妆数据。",
            "access_status": "fetched",
        },
    )

    references = collect_recent_references("高端粉底市场趋势", limit=10, timeout=1)

    assert len(references) == 10
    assert all(is_allowed_result_url(ref["url"]) for ref in references)
    assert all(ref["publisher"] for ref in references)
    assert sum(is_user_requested_source(ref["publisher"]) for ref in references) >= 8


def test_collect_recent_references_debug_exposes_final_and_rejected_candidates(monkeypatch):
    monkeypatch.setattr("web_access_research.build_search_queries", lambda topic: [])
    monkeypatch.setattr("web_access_research.discover_source_candidates", lambda *args, **kwargs: [])

    def fake_enrich(candidate, session, timeout):
        status = "product_page" if "Mintel" in candidate["title"] else "fetched"
        score = 25 if "Kantar" in candidate["title"] else 80
        return {
            **candidate,
            "published_at": "2025-01-01",
            "summary": candidate["title"],
            "content_text": "中国高端粉底美妆市场趋势，销售额100亿元，同比增长9%。",
            "content_excerpt": "中国高端粉底美妆市场趋势，销售额100亿元，同比增长9%。",
            "access_status": status,
            "match_score": score,
        }

    monkeypatch.setattr("web_access_research.enrich_reference", fake_enrich)

    payload = collect_recent_references_debug("高端粉底市场趋势", limit=5, timeout=1)

    assert payload["final_results"]
    assert all(ref["access_status"] == "fetched" for ref in payload["final_results"])
    assert all(ref["match_score"] >= 50 for ref in payload["final_results"])
    assert payload["rejected_results"]
    assert any("reject_reason" in ref for ref in payload["rejected_results"])


def test_collect_recent_references_debug_uses_duckduckgo_and_baidu(monkeypatch):
    monkeypatch.setattr("web_access_research.discover_source_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr("web_access_research.REQUESTED_REFERENCE_SEEDS", [])
    monkeypatch.setattr("web_access_research.CURATED_REFERENCE_SEEDS", [])
    monkeypatch.setattr("web_access_research.build_search_queries", lambda topic: ["美妆 报告"])

    calls = []

    def fake_duckduckgo(query, session, timeout):
        calls.append(("duckduckgo", query))
        return [
            {
                "title": "DuckDuckGo 粉底 Report",
                "url": "https://example.com/ddg-report",
            }
        ]

    def fake_baidu(query, session, timeout):
        calls.append(("baidu", query))
        return [
            {
                "title": "Baidu 粉底 Report",
                "url": "https://example.com/baidu-report",
            }
        ]

    def fake_bing(query, session, timeout):
        calls.append(("bing", query))
        return [
            {
                "title": "Bing 粉底 Report",
                "url": "https://example.com/bing-report",
            }
        ]

    def fake_so360(query, session, timeout):
        calls.append(("so360", query))
        return [
            {
                "title": "360 粉底 Report",
                "url": "https://example.com/so360-report",
            }
        ]

    def fake_enrich(candidate, session, timeout):
        return {
            **candidate,
            "publisher": "example.com",
            "source_type": "media",
            "published_at": "2025-01-01",
            "summary": candidate["title"],
            "content_text": "美妆高端粉底市场趋势报告，销售额100亿元，同比增长9%。",
            "content_excerpt": "美妆高端粉底市场趋势报告，销售额100亿元，同比增长9%。",
            "access_status": "fetched",
        }

    monkeypatch.setattr("web_access_research.search_duckduckgo", fake_duckduckgo)
    monkeypatch.setattr("web_access_research.search_baidu", fake_baidu)
    monkeypatch.setattr("web_access_research.search_bing", fake_bing)
    monkeypatch.setattr("web_access_research.search_so360", fake_so360)
    monkeypatch.setattr("web_access_research.enrich_reference", fake_enrich)

    payload = collect_recent_references_debug("高端粉底市场趋势", limit=10, timeout=1)

    assert ("duckduckgo", "美妆 报告") in calls
    assert ("baidu", "美妆 报告") in calls
    assert ("bing", "美妆 报告") in calls
    assert ("so360", "美妆 报告") in calls
    assert {ref["title"] for ref in payload["final_results"]} == {
        "DuckDuckGo 粉底 Report",
        "Baidu 粉底 Report",
        "Bing 粉底 Report",
        "360 粉底 Report",
    }


def test_scrapfly_fetch_uses_cache_cost_budget_and_reports_cost(monkeypatch):
    monkeypatch.setattr(research, "SCRAPFLY_API_KEY", "test-key")
    monkeypatch.setattr(research, "SCRAPFLY_CACHE_TTL", 604800)

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {
            "X-Scrapfly-Api-Cost": "2",
            "X-Scrapfly-Remaining-Api-Credit": "998",
        }

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "content": "<html>ok</html>",
                    "status_code": 200,
                    "url": "https://example.com/final",
                    "response_headers": {"content-type": "text/html"},
                },
                "context": {"cache": {"state": "HIT"}},
            }

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(research.requests, "get", fake_get)

    response = research._scrapfly_fetch(
        "https://example.com/search",
        params={"q": "彩棠 粉饼"},
        timeout=12,
        cost_budget=3,
    )

    assert captured["url"] == research.SCRAPFLY_ENDPOINT
    assert captured["params"]["cache"] == "true"
    assert captured["params"]["cache_ttl"] == "604800"
    assert captured["params"]["cost_budget"] == "3"
    assert "q=%E5%BD%A9%E6%A3%A0+%E7%B2%89%E9%A5%BC" in captured["params"]["url"]
    assert response.cost == 2
    assert response.remaining_credit == 998
    assert response.cache_state == "HIT"


def test_collect_recent_references_debug_respects_budget_limits(monkeypatch):
    monkeypatch.setattr(research, "SCRAPFLY_API_KEY", "test-key")
    monkeypatch.setattr(research, "RESEARCH_MAX_SEARCH_REQUESTS", 3)
    monkeypatch.setattr(research, "RESEARCH_MAX_FETCH_PAGES", 2)
    monkeypatch.setattr(research, "RESEARCH_TARGET_REFERENCES", 1)
    monkeypatch.setattr(research, "REQUESTED_REFERENCE_SEEDS", [])
    monkeypatch.setattr(research, "CURATED_REFERENCE_SEEDS", [])
    monkeypatch.setattr(research, "discover_source_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(research, "build_search_queries", lambda topic: ["粉饼 数据", "粉饼 市场"])

    calls = {"search": 0, "fetch": 0}

    def fake_search(query, session, timeout):
        calls["search"] += 1
        return [
            {
                "title": f"彩棠粉饼资料 {calls['search']}",
                "url": f"https://example.com/report-{calls['search']}",
                "snippet": "彩棠 粉饼 市场 数据",
            }
        ]

    def fake_enrich(candidate, session, timeout):
        calls["fetch"] += 1
        return {
            **candidate,
            "publisher": "example.com",
            "source_type": "media",
            "published_at": "2025-01-01",
            "summary": candidate["title"],
            "content_text": "彩棠粉饼市场数据报告，销售额100亿元，同比增长9%。",
            "content_excerpt": "彩棠粉饼市场数据报告，销售额100亿元，同比增长9%。",
            "access_status": "fetched",
        }

    monkeypatch.setattr(research, "search_duckduckgo", fake_search)
    monkeypatch.setattr(research, "search_baidu", fake_search)
    monkeypatch.setattr(research, "search_bing", fake_search)
    monkeypatch.setattr(research, "search_so360", fake_search)
    monkeypatch.setattr(research, "enrich_reference", fake_enrich)

    payload = research.collect_recent_references_debug("彩棠粉饼", limit=10, timeout=1)

    assert calls["search"] == 3
    assert calls["fetch"] == 2
    assert len(payload["final_results"]) == 1
    assert payload["budget"]["search_request_limit"] == 3
    assert payload["budget"]["fetch_page_limit"] == 2
    assert payload["budget"]["target_references"] == 1


def test_collect_recent_references_debug_uses_search_snippet_fallback(monkeypatch):
    monkeypatch.setattr(research, "SCRAPFLY_API_KEY", "")
    monkeypatch.setattr(research, "REQUESTED_REFERENCE_SEEDS", [])
    monkeypatch.setattr(research, "CURATED_REFERENCE_SEEDS", [])
    monkeypatch.setattr(research, "discover_source_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(research, "build_search_queries", lambda topic: ['"花西子" 散粉 报告'])
    monkeypatch.setattr(research, "RESEARCH_MAX_SEARCH_REQUESTS", 1)
    monkeypatch.setattr(research, "RESEARCH_MAX_FETCH_PAGES", 4)
    monkeypatch.setattr(research, "RESEARCH_TARGET_REFERENCES", 2)
    monkeypatch.setattr(research, "search_baidu", lambda *args, **kwargs: [])
    monkeypatch.setattr(research, "search_bing", lambda *args, **kwargs: [])
    monkeypatch.setattr(research, "search_so360", lambda *args, **kwargs: [])

    monkeypatch.setattr(
        research,
        "search_duckduckgo",
        lambda *args, **kwargs: [
            {
                "title": "花西子散粉市场数据报告",
                "url": "https://news.qq.com/rain/a/example",
                "snippet": "花西子 散粉 彩妆 市场 数据 报告显示销售额增长12%。",
            }
        ],
    )
    monkeypatch.setattr(research, "enrich_reference", lambda *args, **kwargs: None)

    payload = research.collect_recent_references_debug("花西子 散粉 花西子散粉", limit=2, timeout=1)

    assert payload["final_results"]
    assert payload["final_results"][0]["access_status"] == "thin_content"
    assert payload["final_results"][0]["publisher"] == "news.qq.com"


def test_safe_search_retries_scrapfly_rate_limit_then_recovers(monkeypatch):
    monkeypatch.setattr(research, "SCRAPFLY_API_KEY", "test-key")

    attempts = {"count": 0}

    def fake_scrapfly_fetch(url, params=None, timeout=30, render_js=False, country="cn", cost_budget=None):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return research._ScrapflyResponse(
                429,
                "",
                "https://example.com/search?q=test",
                {},
                cost=0,
                remaining_credit=999,
                cache_state="MISS",
            )
        return research._ScrapflyResponse(
            200,
            "<html>search ok</html>",
            "https://example.com/search?q=test",
            {"content-type": "text/html"},
            cost=1,
            remaining_credit=999,
            cache_state="MISS",
        )

    sleep_calls = []

    monkeypatch.setattr(research, "_scrapfly_fetch", fake_scrapfly_fetch)
    monkeypatch.setattr(research.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    session = research.requests.Session()
    text = research._safe_search(
        session,
        "https://www.baidu.com/s",
        {"wd": '"香奈儿" 香水'},
        timeout=10,
        headers={},
    )

    assert text == "<html>search ok</html>"
    assert attempts["count"] == 3
    assert sleep_calls


def test_safe_search_does_not_slow_retry_non_rate_limit_scrapfly_failure(monkeypatch):
    monkeypatch.setattr(research, "SCRAPFLY_API_KEY", "test-key")

    attempts = {"count": 0}

    def fake_scrapfly_fetch(url, params=None, timeout=30, render_js=False, country="cn", cost_budget=None):
        attempts["count"] += 1
        return None

    sleep_calls = []

    monkeypatch.setattr(research, "_scrapfly_fetch", fake_scrapfly_fetch)
    monkeypatch.setattr(research.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    session = research.requests.Session()
    text = research._safe_search(
        session,
        "https://www.bing.com/search",
        {"q": '"香奈儿" 香水'},
        timeout=10,
        headers={},
    )

    assert text == ""
    assert attempts["count"] == 1
    assert sleep_calls == []


def test_ai_reference_selection_can_reject_authoritative_but_wrong_category_pages(monkeypatch):
    refs = [
        {
            "title": "食品与饮料资讯平台",
            "url": "https://china.mintel.com/products/food-and-drink-platform/",
            "publisher": "china.mintel.com",
            "source_type": "institution",
            "access_status": "fetched",
            "match_score": 72,
            "summary": "Mintel 食品饮料消费趋势。",
            "content_excerpt": "食品饮料平台，覆盖饮料、零食、餐饮消费。",
        },
        {
            "title": "美容与个人护理资讯平台",
            "url": "https://china.mintel.com/products/beauty-and-personal-care-platform/",
            "publisher": "china.mintel.com",
            "source_type": "institution",
            "access_status": "fetched",
            "match_score": 62,
            "summary": "Mintel 美容与个人护理市场洞察。",
            "content_excerpt": "覆盖美容、个人护理、彩妆、护肤消费趋势。",
        },
    ]

    monkeypatch.setattr(research, "RESEARCH_AI_RERANK_ENABLED", True)
    monkeypatch.setattr(research, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        research,
        "_call_ai_reference_judge",
        lambda topic, candidates, limit, timeout=45: [
            {
                "url": "https://china.mintel.com/products/food-and-drink-platform/",
                "usable": False,
                "relevance_score": 8,
                "data_score": 15,
                "authority_score": 90,
                "reason": "食品饮料页面，不适合 TF 眼影报告。",
            },
            {
                "url": "https://china.mintel.com/products/beauty-and-personal-care-platform/",
                "usable": True,
                "relevance_score": 76,
                "data_score": 45,
                "authority_score": 90,
                "reason": "美容个护平台，可作为品类背景。",
            },
        ],
    )

    selected, rejected = research.ai_select_references(refs, "TF 眼影 TF眼影", limit=10)

    assert [ref["title"] for ref in selected] == ["美容与个人护理资讯平台"]
    assert selected[0]["ai_relevance_score"] == 76
    assert rejected[0]["reject_reason"] == "ai_rejected"
    assert "食品饮料" in rejected[0]["ai_reason"]


def test_ai_reference_selection_falls_back_to_rule_sorting_when_ai_unavailable(monkeypatch):
    refs = [
        {
            "title": "彩妆市场报告",
            "url": "https://example.com/makeup-report",
            "publisher": "example.com",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 65,
            "required_terms_matched": ["眼影"],
            "content_excerpt": "眼影彩妆市场规模100亿元，同比增长9%。",
        }
    ]

    monkeypatch.setattr(research, "RESEARCH_AI_RERANK_ENABLED", True)
    monkeypatch.setattr(research, "DEEPSEEK_API_KEY", "")

    selected, rejected = research.ai_select_references(refs, "TF 眼影 TF眼影", limit=10)

    assert selected == refs
    assert rejected == []


def test_ai_reference_selection_keeps_fallback_context_when_ai_rejects_everything(monkeypatch):
    refs = [
        {
            "title": "兰蔻极光水护肤系列",
            "url": "https://zh.lancome-usa.com/skincare/clarifique/",
            "publisher": "zh.lancome-usa.com",
            "source_type": "official",
            "access_status": "fetched",
            "match_score": 70,
            "required_terms_matched": ["兰蔻", "极光水乳"],
            "content_excerpt": "兰蔻极光水护肤系列，保湿、美白、焕肤。",
        },
        {
            "title": "兰蔻品牌百科",
            "url": "https://m.baike.com/wikiid/7198048903274168335",
            "publisher": "m.baike.com",
            "source_type": "media",
            "access_status": "fetched",
            "match_score": 60,
            "required_terms_matched": ["兰蔻"],
            "content_excerpt": "兰蔻品牌介绍。",
        },
        {
            "title": "兰蔻极光水乳电商参数",
            "url": "https://www.suning.com/itemcanshu/123.html",
            "publisher": "suning.com",
            "source_type": "media",
            "access_status": "thin_content",
            "match_score": 54,
            "required_terms_matched": ["兰蔻", "极光水乳"],
            "content_excerpt": "兰蔻极光水乳套装参数。",
        },
    ]

    monkeypatch.setattr(research, "RESEARCH_AI_RERANK_ENABLED", True)
    monkeypatch.setattr(research, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        research,
        "_call_ai_reference_judge",
        lambda topic, candidates, limit, timeout=45: [
            {
                "url": ref["url"],
                "usable": False,
                "relevance_score": 35,
                "data_score": 5,
                "authority_score": 60,
                "reason": "资料数据价值不足。",
            }
            for ref in refs
        ],
    )

    selected, rejected = research.ai_select_references(refs, "兰蔻 极光水乳 保湿", limit=10)

    assert selected
    assert selected[0]["title"] == "兰蔻极光水护肤系列"
    assert selected[0]["ai_fallback"] is True
    assert all(ref["publisher"] != "suning.com" for ref in selected)
    assert any(ref["reject_reason"] == "ai_rejected" for ref in rejected)
