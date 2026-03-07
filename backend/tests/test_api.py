import time


def test_disclaimer_flow(client):
    first = client.get("/api/app-state")
    assert first.status_code == 200
    assert first.json()["launch_disclaimer_required"] is True

    consent = client.post(
        "/api/risk-consents",
        json={"consent_type": "launch_disclaimer", "version": "1.0.0"},
    )
    assert consent.status_code == 200

    second = client.get("/api/app-state")
    assert second.json()["launch_disclaimer_required"] is False


def test_search_pipeline_returns_matches(client):
    client.put(
        "/api/profile",
        json={
            "id": 1,
            "full_name": "Test Candidate",
            "headline": "Senior Frontend Engineer",
            "summary": "React and TypeScript engineer",
            "target_roles": ["前端工程师", "全栈工程师"],
            "preferred_cities": ["上海", "杭州"],
            "salary_floor": 25000,
            "years_experience": 5,
            "degree": "本科",
            "skills": ["React", "TypeScript", "Node.js", "FastAPI"],
            "must_have_keywords": ["React", "TypeScript"],
            "source_filename": None,
            "source_language": "zh-CN"
        },
    )

    response = client.post(
        "/api/search-sessions",
        json={
            "platform": "boss",
            "mode": "recommend_only",
            "job_targets": ["前端工程师", "全栈工程师"],
            "cities": ["上海", "杭州"],
            "salary_floor": 25000,
            "must_have_keywords": ["React", "TypeScript"],
        },
    )
    assert response.status_code == 200
    session_id = response.json()["id"]

    deadline = time.time() + 5
    status = "running"
    while time.time() < deadline:
        status_response = client.get(f"/api/search-sessions/{session_id}")
        status = status_response.json()["status"]
        if status == "ready":
            break
        time.sleep(0.15)

    assert status == "ready"
    matches = client.get(f"/api/search-sessions/{session_id}/matches")
    assert matches.status_code == 200
    payload = matches.json()
    assert len(payload) >= 1
    assert payload[0]["final_score"] >= payload[0]["rule_score"] * 0.6


def test_guided_apply_requires_consent_and_respects_emergency_stop(client):
    client.put(
        "/api/profile",
        json={
            "id": 1,
            "full_name": "Safe User",
            "headline": "Frontend Engineer",
            "summary": "",
            "target_roles": ["前端工程师"],
            "preferred_cities": ["上海"],
            "salary_floor": 25000,
            "years_experience": 4,
            "degree": "本科",
            "skills": ["React", "TypeScript"],
            "must_have_keywords": ["React"],
            "source_filename": None,
            "source_language": "zh-CN"
        },
    )
    session_response = client.post(
        "/api/search-sessions",
        json={
            "platform": "boss",
            "mode": "recommend_only",
            "job_targets": ["前端工程师"],
            "cities": ["上海"],
            "salary_floor": 25000,
            "must_have_keywords": ["React"],
        },
    )
    session_id = session_response.json()["id"]

    deadline = time.time() + 5
    while time.time() < deadline:
      if client.get(f"/api/search-sessions/{session_id}").json()["status"] == "ready":
          break
      time.sleep(0.15)

    job_id = client.get(f"/api/search-sessions/{session_id}/matches").json()[0]["job_id"]
    no_consent = client.post(f"/api/jobs/{job_id}/guided-apply")
    assert no_consent.status_code == 403

    client.post(
        "/api/risk-consents",
        json={"consent_type": "guided_apply", "platform": "boss", "version": "1.0.0"},
    )
    client.post("/api/emergency-stop", json={"active": True})
    blocked = client.post(f"/api/jobs/{job_id}/guided-apply")
    assert blocked.status_code == 409
