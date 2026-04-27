import os
import tempfile

from reflection_agent import ReflectionAgent
import proxy


def test_evaluate_and_reflect_generates_fallback_reflection_for_reports():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = os.path.join(tmpdir, "reflections.json")
        agent = ReflectionAgent(storage_path=storage_path)

        response = """
# 高端粉底市场趋势白皮书

## 执行摘要
中国高端底妆市场仍在增长，品牌竞争正在从单品竞争转向科技与渠道效率竞争。

## 研究说明
报告基于近两年公开财报、机构报告和行业访谈资料撰写。

## 结论与行动建议
- 加强线下体验与会员运营
- 优先验证高端底妆复购与客单提升
"""

        session = agent.evaluate_and_reflect(
            query="生成高端粉底市场趋势白皮书",
            response=response,
            reflection="",
            session_id="report_session",
        )

        assert session.reflection.strip()
        assert session.reflection_mode == "auto_generated"
        assert "I recognize" in session.reflection
        assert agent.get_reflection_session("report_session") is not None
        assert session.evaluation_result.overall_score > 0.3


def test_evaluate_and_reflect_uses_source_consistency_mode_when_references_exist():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = os.path.join(tmpdir, "reflections.json")
        agent = ReflectionAgent(storage_path=storage_path)

        response = """
# 高端粉底市场趋势白皮书

## 执行摘要
高端底妆市场正在由功效护肤、线下体验和品牌研发投入共同驱动。

## 研究说明
报告基于公开财报、机构报告和权威行业资料撰写。

## 结论与行动建议
- 优先关注高端底妆复购率与线下体验转化
- 将研发投入和消费者教育作为长期竞争壁垒

---

## 参考资料与链接

1. [L'Oréal Annual Report 2024](https://www.loreal-finance.com/en/annual-report-2024/)
   发布方：loreal-finance.com ｜ 类型：official ｜ 日期：2025-03-24
2. [Circana US Prestige & Mass Beauty Retail Performance 2025](https://www.circana.com/post/us-prestige-and-mass-beauty-retail-deliver-a-positive-performance-in-2025-circana-reports)
   发布方：circana.com ｜ 类型：institution ｜ 日期：2026-02-10
"""

        session = agent.evaluate_and_reflect(
            query="生成高端粉底市场趋势白皮书",
            response=response,
            reflection="",
            session_id="source_consistency_session",
        )

        assert session.reflection_mode == "source_consistency"
        assert "Source Consistency" in session.reflection
        assert "trusted reference links" in session.reflection
        assert "loreal-finance.com" in session.reflection
        assert session.evaluation_result.overall_score > 0.3


def test_source_consistency_reflection_uses_system_threshold():
    assert proxy._reflection_pass_threshold("source_consistency") == 0.35
    assert proxy._reflection_pass_threshold("auto_generated") == 0.35
    assert proxy._reflection_pass_threshold("user") == 0.7


def test_source_consistency_skips_legacy_number_verification():
    assert proxy._should_run_legacy_data_verification("source_consistency") is False
    assert proxy._should_run_legacy_data_verification("auto_generated") is True
    assert proxy._should_run_legacy_data_verification("user") is True
