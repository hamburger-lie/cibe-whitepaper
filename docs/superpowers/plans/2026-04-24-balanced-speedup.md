# CIBE 白皮书均衡提速 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在尽量不牺牲资料质量和正文质量的前提下，缩短白皮书生成的平均等待时间并减少“卡一下”的体感。

**Architecture:** 研究链路增加本地缓存和分批提前收敛机制，避免每次都把搜索和抓取预算跑满；生成链路增加轻量级快速通过规则，让高质量首稿跳过昂贵的改写回路。整体保持现有四代理和参考资料流程不变。

**Tech Stack:** Python, FastAPI, requests, ThreadPoolExecutor, pytest, JSON file cache

---

### Task 1: 为研究链路补缓存与提前收敛测试

**Files:**
- Modify: `D:/workspace/buddy/tests/test_web_access_research_filters.py`
- Modify: `D:/workspace/buddy/tests/test_chart_safety.py`

- [ ] **Step 1: 写缓存命中测试**

```python
def test_collect_recent_references_debug_uses_cache_before_search(...):
    ...
```

- [ ] **Step 2: 写反思快速通过测试**

```python
def test_should_skip_reflection_for_high_confidence_whitepaper():
    ...
```

- [ ] **Step 3: 运行定向测试并确认失败**

Run: `python -m pytest tests\\test_web_access_research_filters.py::test_collect_recent_references_debug_uses_cache_before_search tests\\test_chart_safety.py::test_should_skip_reflection_for_high_confidence_whitepaper -q`

- [ ] **Step 4: 记录失败现象并开始实现**

Expected: 因缺少缓存函数/快速通过函数而失败

### Task 2: 实现研究缓存与分批抓取提前收敛

**Files:**
- Modify: `D:/workspace/buddy/web_access_research.py`
- Test: `D:/workspace/buddy/tests/test_web_access_research_filters.py`

- [ ] **Step 1: 增加研究缓存读写函数与配置**
- [ ] **Step 2: 在 `collect_recent_references_debug` 开头优先读缓存**
- [ ] **Step 3: 把候选抓取改成分批执行，每批结束判断是否已达到目标**
- [ ] **Step 4: 生成成功后写回缓存**
- [ ] **Step 5: 运行研究相关测试**

Run: `python -m pytest tests\\test_web_access_research_filters.py -q`

### Task 3: 实现反思快速通过

**Files:**
- Modify: `D:/workspace/buddy/proxy.py`
- Test: `D:/workspace/buddy/tests/test_chart_safety.py`

- [ ] **Step 1: 增加首稿快速通过判定函数**
- [ ] **Step 2: 在 `run_four_agent_pipeline` 中根据参考资料数量和正文质量决定是否跳过反思**
- [ ] **Step 3: 保留低质量场景下的完整反思改写链路**
- [ ] **Step 4: 运行反思与图表安全测试**

Run: `python -m pytest tests\\test_chart_safety.py tests\\test_report_references.py tests\\test_research_endpoint.py -q`

### Task 4: 端到端验证与重启服务

**Files:**
- Modify: `D:/workspace/buddy/web_access_research.py`
- Modify: `D:/workspace/buddy/proxy.py`

- [ ] **Step 1: 运行语法检查**

Run: `python -m py_compile web_access_research.py proxy.py web_search.py`

- [ ] **Step 2: 运行核心回归**

Run: `python -m pytest tests\\test_web_access_research_filters.py tests\\test_chart_safety.py tests\\test_report_references.py tests\\test_research_endpoint.py -q`

- [ ] **Step 3: 重启后端并检查健康接口**

Run: `Invoke-RestMethod -Uri http://127.0.0.1:5678/api/health`

