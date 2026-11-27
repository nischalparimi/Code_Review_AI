"""API tests for the FastAPI adapter around the existing analyzer."""

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import analysis as analysis_service

client = TestClient(app)


def test_health_and_rules_endpoints():
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/api/rules")
    assert response.status_code == 200
    assert len(response.json()) == 14
    assert {rule["rule_id"] for rule in response.json()} >= {"STYLE001", "SEC001", "MAINT001", "SEC003", "SMELL003"}


def test_analyze_pasted_source_returns_findings_and_quality_gate():
    response = client.post("/api/analyze", json={
        "filename": "folder/example.py",
        "source_code": "def run():\n    return eval('1 + 1')\n",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["total_issues"] >= 1
    assert data["summary"]["critical"] == 1
    assert data["files"][0]["file"] == "example.py"
    assert data["quality_score"]["score"] == max(0, 100 - data["summary"]["critical"] * 15 - data["summary"]["warning"] * 5 - data["summary"]["info"])
    assert data["quality_score"]["grade"] == "B"
    assert data["quality_score"]["severity_counts"] == data["summary"]
    eval_issue = next(issue for issue in data["files"][0]["issues"] if issue["rule_id"] == "SEC001")
    assert eval_issue["line"] == 2
    assert "ast.literal_eval" in eval_issue["remediation"]
    assert data["quality_gate"] == {"blocking_severities": ["critical"], "passed": False}
    assert "code_review_" not in str(data)


def test_upload_and_parse_error_are_reported():
    response = client.post(
        "/api/analyze/file",
        files={"file": ("broken.py", b"def broken(:\n pass\n", "text/x-python")},
    )
    assert response.status_code == 200
    file_result = response.json()["files"][0]
    assert file_result["file"] == "broken.py"
    assert file_result["parse_error"].startswith("Syntax error:")
    assert file_result["issues"] == []
    assert response.json()["quality_score"]["score"] == 100
    assert response.json()["quality_score"]["parse_error_count"] == 1


def test_uploaded_findings_are_scored_from_the_actual_issues():
    response = client.post(
        "/api/analyze/file",
        files={"file": ("findings.py", b"first = eval('1')\nsecond = eval('2')\n", "text/x-python")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quality_score"]["severity_counts"] == data["summary"]
    assert data["summary"]["critical"] == 2
    assert data["quality_score"]["score"] == 70
    assert data["quality_score"]["grade"] == "C"


def test_invalid_inputs_and_oversized_upload_are_rejected():
    assert client.post("/api/analyze", json={"filename": "main.txt", "source_code": "pass"}).status_code == 422
    empty = client.post("/api/analyze", json={"filename": "main.py", "source_code": " "})
    assert empty.status_code == 200
    assert empty.json()["quality_score"]["score"] == 100
    assert client.post(
        "/api/analyze/file",
        files={"file": ("main.txt", b"pass", "text/plain")},
    ).status_code == 422
    too_big = b" " * (analysis_service.MAX_SOURCE_BYTES + 1)
    response = client.post("/api/analyze/file", files={"file": ("large.py", too_big, "text/x-python")})
    assert response.status_code == 413


def test_temp_file_is_removed_after_analysis(monkeypatch):
    created_paths = []
    named_temporary_file = analysis_service.tempfile.NamedTemporaryFile

    def tracking_temporary_file(*args, **kwargs):
        temp = named_temporary_file(*args, **kwargs)
        created_paths.append(temp.name)
        return temp

    monkeypatch.setattr(analysis_service.tempfile, "NamedTemporaryFile", tracking_temporary_file)
    result = analysis_service.analyze_source("pass\n", "clean.py")
    assert result["total_issues"] == 0
    assert len(created_paths) == 1
    assert not analysis_service.os.path.exists(created_paths[0])


def test_invalid_severity_is_rejected():
    response = client.post("/api/analyze", json={
        "filename": "main.py", "source_code": "pass", "fail_on": ["fatal"],
    })
    assert response.status_code == 422


def test_validation_errors_do_not_echo_submitted_values():
    secret_marker = "private-input-marker-should-not-be-echoed"
    response = client.post("/api/analyze", json={
        "filename": secret_marker,
        "source_code": [secret_marker],
    })
    assert response.status_code == 422
    assert secret_marker not in response.text


def test_quality_gate_accepts_new_rule_severities_and_source_is_not_executed():
    critical = client.post("/api/analyze", json={
        "filename": "process.py",
        "source_code": "import subprocess\nsubprocess.run(user_command, shell=True)\n",
        "fail_on": ["critical"],
    }).json()
    assert critical["quality_gate"]["passed"] is False
    assert any(issue["rule_id"] == "SEC003" for issue in critical["files"][0]["issues"])

    warning = client.post("/api/analyze", json={
        "filename": "hashing.py",
        "source_code": "import hashlib\nhashlib.md5(b'value')\n",
        "fail_on": ["warning"],
    }).json()
    assert warning["quality_gate"]["passed"] is False
    assert any(issue["rule_id"] == "SEC004" for issue in warning["files"][0]["issues"])

    inert = client.post("/api/analyze", json={
        "filename": "inert.py",
        "source_code": "raise RuntimeError('this source must not execute')\n",
    })
    assert inert.status_code == 200
    assert inert.json()["files"][0]["parse_error"] is None


def test_upload_empty_file_scores_100_and_gate_remains_independent():
    response = client.post(
        "/api/analyze/file",
        files={"file": ("empty.py", b"", "text/x-python")},
        data={"fail_on": "critical,warning,info"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quality_score"]["score"] == 100
    assert data["quality_score"]["grade"] == "A"
    assert data["quality_gate"]["passed"] is True
    assert data["total_issues"] == 0
