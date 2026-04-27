from fastapi.testclient import TestClient

import proxy


client = TestClient(proxy.app)


def setup_function():
    proxy.AUTH_ENABLED = False


def test_sqlite_user_password_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")

    proxy._init_app_db()

    assert proxy._verify_user_password("admin", "secret")
    assert not proxy._verify_user_password("admin", "wrong")


def test_generation_job_queue_persists_and_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(proxy, "ENABLE_WEB_SEARCH", False)
    monkeypatch.setattr(proxy, "run_four_agent_pipeline", lambda data_text, research_context="", references=None: "# queued ok")
    proxy._init_app_db()

    job_id = proxy._create_generation_job("admin", "测试输入")
    proxy._run_generation_job(job_id)
    job = proxy._get_generation_job(job_id)

    assert job["status"] == "succeeded"
    assert job["markdown"] == "# queued ok"


def test_jobs_are_isolated_by_username(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    proxy._init_app_db()
    proxy._create_user("tester01", "secret123", role="user")
    proxy._create_generation_job("admin", "admin data", "job-admin")
    proxy._create_generation_job("tester01", "user data", "job-user")

    admin_jobs = proxy._list_generation_jobs("admin")
    user_jobs = proxy._list_generation_jobs("tester01")

    assert [job["id"] for job in admin_jobs] == ["job-admin"]
    assert [job["id"] for job in user_jobs] == ["job-user"]


def test_batch_create_users(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    proxy._init_app_db()

    created = proxy._batch_create_users(prefix="tester", count=3)

    assert len(created) == 3
    assert created[0]["username"] == "tester01"
    assert all(item["password"] for item in created)


def test_auth_blocks_generate_until_login(monkeypatch):
    proxy.AUTH_ENABLED = True
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    monkeypatch.setattr(proxy, "AUTH_SECRET", "test-secret")

    blocked = client.post("/api/generate", data={"text": "测试"})
    assert blocked.status_code == 401

    login = client.post("/api/auth/login", data={"username": "admin", "password": "secret"})
    assert login.status_code == 200
    assert proxy.AUTH_COOKIE_NAME in login.cookies

    monkeypatch.setattr(proxy, "_create_generation_job", lambda username, data_text, job_id=None: "auth-test-job")
    monkeypatch.setattr(proxy, "_enqueue_generation_job", lambda job_id: None)
    allowed = client.post(
        "/api/generate",
        data={"text": "测试", "job_id": "auth-test-job"},
        cookies={proxy.AUTH_COOKIE_NAME: login.cookies.get(proxy.AUTH_COOKIE_NAME)},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "queued"
    assert allowed.json()["job_id"] == "auth-test-job"


def test_admin_user_endpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    proxy.AUTH_ENABLED = True
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    monkeypatch.setattr(proxy, "AUTH_SECRET", "test-secret")
    proxy._init_app_db()

    login = client.post("/api/auth/login", data={"username": "admin", "password": "secret"})
    cookies = {proxy.AUTH_COOKIE_NAME: login.cookies.get(proxy.AUTH_COOKIE_NAME)}

    created = client.post(
        "/api/admin/users",
        data={"username": "tester09", "password": "secret123", "role": "user"},
        cookies=cookies,
    )
    assert created.status_code == 200
    assert created.json()["user"]["username"] == "tester09"

    listed = client.get("/api/admin/users", cookies=cookies)
    assert listed.status_code == 200
    assert any(user["username"] == "tester09" for user in listed.json()["users"])


def test_admin_dashboard_and_cross_user_job_access(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    proxy.AUTH_ENABLED = True
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    monkeypatch.setattr(proxy, "AUTH_SECRET", "test-secret")
    proxy._init_app_db()
    proxy._create_user("tester02", "secret123", role="user")
    proxy._create_generation_job("tester02", "【文字输入】\n测试品牌数据", "job-tester02")
    proxy._update_generation_job("job-tester02", status="succeeded", markdown="# 测试白皮书\n\n内容")

    login = client.post("/api/auth/login", data={"username": "admin", "password": "secret"})
    cookies = {proxy.AUTH_COOKIE_NAME: login.cookies.get(proxy.AUTH_COOKIE_NAME)}

    dashboard = client.get("/api/admin/dashboard", cookies=cookies)
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["metrics"]["user_count"] >= 2
    assert payload["metrics"]["job_count"] >= 1
    assert any(job["id"] == "job-tester02" for job in payload["recent_jobs"])

    job_detail = client.get("/api/admin/jobs/job-tester02", cookies=cookies)
    assert job_detail.status_code == 200
    assert job_detail.json()["job"]["username"] == "tester02"
    assert "# 测试白皮书" in job_detail.json()["job"]["markdown"]


def test_user_can_delete_own_job(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    proxy.AUTH_ENABLED = True
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    monkeypatch.setattr(proxy, "AUTH_SECRET", "test-secret")
    proxy._init_app_db()
    proxy._create_generation_job("admin", "【文字输入】\n测试删除", "job-delete-me")

    login = client.post("/api/auth/login", data={"username": "admin", "password": "secret"})
    cookies = {proxy.AUTH_COOKIE_NAME: login.cookies.get(proxy.AUTH_COOKIE_NAME)}

    deleted = client.delete("/api/jobs/job-delete-me", cookies=cookies)
    assert deleted.status_code == 200
    assert proxy._get_generation_job("job-delete-me") is None


def test_admin_can_delete_any_job(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "APP_DB_PATH", str(tmp_path / "app.db"))
    proxy.AUTH_ENABLED = True
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    monkeypatch.setattr(proxy, "AUTH_SECRET", "test-secret")
    proxy._init_app_db()
    proxy._create_user("tester03", "secret123", role="user")
    proxy._create_generation_job("tester03", "【文字输入】\n用户任务", "job-user-delete")

    login = client.post("/api/auth/login", data={"username": "admin", "password": "secret"})
    cookies = {proxy.AUTH_COOKIE_NAME: login.cookies.get(proxy.AUTH_COOKIE_NAME)}

    deleted = client.delete("/api/admin/jobs/job-user-delete", cookies=cookies)
    assert deleted.status_code == 200
    assert proxy._get_generation_job("job-user-delete") is None


def test_research_sources_endpoint_returns_search_results(monkeypatch):
    sample_results = [
        {
            "title": "KPMG Beauty Report 2025",
            "url": "https://assets.kpmg.com/example.pdf",
            "source_type": "institution",
            "publisher": "assets.kpmg.com",
            "published_at": "2025-11-14",
            "summary": "Recent beauty market report.",
        }
    ]

    monkeypatch.setattr(proxy, "collect_recent_references", lambda topic, limit, timeout: sample_results)

    response = client.post(
        "/api/research-sources",
        data={"text": "高端粉底市场趋势", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["count"] == 1
    assert payload["results"][0]["url"] == "https://assets.kpmg.com/example.pdf"


def test_research_sources_endpoint_can_return_debug_payload(monkeypatch):
    sample_debug = {
        "final_results": [
            {
                "title": "usable",
                "url": "https://example.com/usable",
                "access_status": "fetched",
                "match_score": 80,
            }
        ],
        "rejected_results": [
            {
                "title": "product",
                "url": "https://example.com/product",
                "access_status": "product_page",
                "match_score": 90,
                "reject_reason": "unusable_status_product_page",
            }
        ],
        "candidate_count": 2,
        "enriched_count": 2,
        "usable_count": 1,
        "min_match_score": 50,
        "usable_statuses": ["fetched"],
    }

    monkeypatch.setattr(proxy, "collect_recent_references_debug", lambda topic, limit, timeout: sample_debug)

    response = client.post(
        "/api/research-sources",
        data={"text": "高端粉底市场趋势", "limit": 5, "debug": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "usable"
    assert payload["debug"]["rejected_results"][0]["reject_reason"] == "unusable_status_product_page"
    assert payload["debug"]["min_match_score"] == 50


def test_progress_stream_returns_emitted_event():
    job_id = "test-progress-job"
    proxy._emit_progress("测试进度消息", job_id=job_id)
    proxy._finish_progress(job_id)

    with client.stream("GET", f"/api/progress/{job_id}") as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "event: progress" in body
    assert "测试进度消息" in body
    assert "event: done" in body
