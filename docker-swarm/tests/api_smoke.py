#!/usr/bin/env python3
"""Authenticated smoke checks for an isolated local AppFlowy deployment.

Run `create`, then run `verify` after service replacement with the same state.
Runtime files default to docker-swarm/.local; SWARM_TEST_DIR overrides that path.
The public URL comes from metadata.json unless SWARM_TEST_BASE_URL is supplied.
Credentials are read only from private runtime files and are never logged.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

runtime_dir = Path(os.environ.get("SWARM_TEST_DIR", Path(__file__).resolve().parents[1] / ".local")).expanduser().resolve()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("phase", choices=["create", "verify"])
parser.add_argument("--state", type=Path, default=runtime_dir / "api-state.json")
parser.add_argument("--skip-search", action="store_true")
parser.add_argument("--skip-import", action="store_true")
parser.add_argument("--timeout", type=int, default=150)
args = parser.parse_args()
metadata = json.loads((runtime_dir / "metadata.json").read_text())
base = os.environ.get("SWARM_TEST_BASE_URL", metadata["base_url"]).rstrip("/")
parsed_base = urllib.parse.urlsplit(base)
if parsed_base.hostname not in ("localhost", "127.0.0.1", "::1"):
    raise SystemExit("This script only accepts a loopback test URL")
token = None
events = []
device = "swarm-smoke-" + uuid.uuid4().hex
state_path = Path(args.state)
state = {}


def private_json(path):
    if path.stat().st_mode & 0o077:
        raise RuntimeError(f"Credential file must have mode 0600: {path.name}")
    return json.loads(path.read_text())


def write_private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)


credentials = private_json(runtime_dir / "credentials.json")
admin_credentials = {"email": credentials["admin_email"], "password": credentials["admin_password"]}
ordinary_path = runtime_dir / "ordinary-user.json"
sensitive_values = set(admin_credentials.values())


def redact(value):
    for secret in sensitive_values | ({token} if token else set()):
        if secret:
            value = value.replace(secret, "[redacted]")
    return value


def record(name, **details):
    event = {"check": name, **details}
    events.append(event)
    print(json.dumps(event), flush=True)


def request(method, path, payload=None, raw=None, content_type=None, label=None, unwrap=True, absolute=False):
    url = path if absolute else base + path
    headers = {"x-platform": "web", "device-id": device,
               "client-timestamp": str(int(time.time())), "x-request-time": str(int(time.time()*1000))}
    if os.environ.get("SWARM_TEST_CLIENT_VERSION"):
        headers["client-version"] = os.environ["SWARM_TEST_CLIENT_VERSION"]
    if token and not absolute:
        headers["Authorization"] = "Bearer " + token
    if payload is not None:
        raw = json.dumps(payload).encode()
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    if path.endswith("/document") and method == "POST":
        headers["X-Host"] = base
    req = urllib.request.Request(url, data=raw, headers=headers, method=method)
    check = label or method + " " + path
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = response.read()
            mime = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        body = redact(body)
        raise RuntimeError(f"{check}: HTTP {exc.code}: {body[:1200]}") from None
    except Exception as exc:
        # Do not log a credential-bearing verification or presigned URL.
        raise RuntimeError(f"{check}: {type(exc).__name__}") from None
    if "json" not in mime and not unwrap:
        return data
    parsed = json.loads(data) if data else None
    if unwrap and isinstance(parsed, dict) and "code" in parsed:
        if parsed["code"] != 0:
            raise RuntimeError(redact(f"{check}: application error {parsed['code']}: {parsed.get('message')}"))
        return parsed.get("data")
    return parsed


def save():
    state_path.write_text(json.dumps(state, indent=2) + "\n")


def read_page(view_id, expected_name=None, marker=None):
    data = request("GET", f"/api/workspace/{state['workspace_id']}/page-view/{view_id}")
    assert data["view"]["view_id"] == view_id, "Page ID differs"
    if expected_name:
        assert data["view"]["name"] == expected_name, "Page name differs"
    collab = bytes(data["data"]["encoded_collab"])
    assert collab, "Page collab is empty"
    # This checks the stored binary payload, not decoded current document text.
    # Yjs updates can retain deleted text; browser tests cover visible content.
    if marker:
        assert marker.encode() in collab, "Expected marker absent from stored document payload"
    return collab


def verify_search():
    deadline = time.monotonic() + args.timeout
    last = None
    while time.monotonic() < deadline:
        try:
            query = urllib.parse.urlencode({"query": state['marker'], "mode": "keyword", "limit": 20, "preview_size": 200})
            results = request("GET", f"/api/search/{state['workspace_id']}?{query}")
            if state["document_id"] in json.dumps(results):
                record("keyword_search", passed=True, matched_document=state["document_id"])
                return
            last = f"No matching document among {len(results or [])} results"
        except Exception as exc:
            last = str(exc)
        time.sleep(3)
    raise AssertionError(f"Keyword search did not return the created document: {last}")


try:
    auth = request("POST", "/gotrue/token?grant_type=password", payload=admin_credentials,
        label="password_login", unwrap=False)
    token = auth["access_token"]
    record("admin_password_login", passed=True)
    # The seeded GoTrue system administrator deliberately has no application
    # workspace. Provision one ordinary test user using the local admin token.
    if ordinary_path.exists():
        ordinary_credentials = private_json(ordinary_path)
    elif args.phase == "create":
        email_local, email_domain = admin_credentials["email"].rsplit("@", 1)
        ordinary_credentials = {"email": email_local + "+user@" + email_domain,
                                "password": admin_credentials["password"]}
        sensitive_values.update(ordinary_credentials.values())
        created = request("POST", "/gotrue/admin/users", payload={**ordinary_credentials, "email_confirm": True},
                          label="create_ordinary_test_user", unwrap=False)
        assert created["email"] == ordinary_credentials["email"], "Created ordinary user email differs"
        created_id = str(uuid.UUID(created["id"]))
        write_private_json(runtime_dir / "ordinary-user-ownership.json",
                           {"user_id": created_id, "email": created["email"]})
        write_private_json(ordinary_path, ordinary_credentials)
        record("create_ordinary_test_user", passed=True)
    else:
        raise RuntimeError("Missing ordinary-user.json; run the create phase first")
    sensitive_values.update(ordinary_credentials.values())
    token = request("POST", "/gotrue/token?grant_type=password", payload=ordinary_credentials,
                    label="ordinary_user_login", unwrap=False)["access_token"]
    record("password_login", passed=True)
    request("GET", "/api/user/verify/" + token, label="cloud_user_verify")
    record("cloud_user_verify", passed=True)
    workspaces = request("GET", "/api/workspace")
    assert workspaces, "No workspace returned"
    record("list_workspaces", passed=True, count=len(workspaces))
    if args.phase == "create":
        state = {"workspace_id": workspaces[0]["workspace_id"], "marker": "swarmproof" + uuid.uuid4().hex[:12]}
        wid = state["workspace_id"]
        folder = request("GET", f"/api/workspace/{wid}/folder?depth=2")
        general = next((v for v in folder["children"] if v["name"] == "General"), None)
        assert general, "Default General space not found"
        state["parent_id"] = general["view_id"]
        state["document_name"] = "Docker Swarm " + state["marker"]
        document = request("POST", f"/api/workspace/{wid}/page-view", payload={
            "parent_view_id": state["parent_id"], "layout": 0, "name": state["document_name"],
            "page_data": {"type": "page", "children": [{"type": "paragraph", "data": {
                "delta": [{"insert": "Persistent document text " + state["marker"]}]}}]}})
        state["document_id"] = document["view_id"]
        save()
        collab = read_page(state["document_id"], state["document_name"], state["marker"])
        state["document_sha256"] = hashlib.sha256(collab).hexdigest()
        record("create_read_document", passed=True, view_id=state["document_id"], collab_bytes=len(collab),
               stored_document_payload_contains_marker=True)
        state["database_name"] = "Swarm database " + state["marker"]
        database = request("POST", f"/api/workspace/{wid}/page-view", payload={
            "parent_view_id": state["parent_id"], "layout": 1, "name": state["database_name"]})
        state["database_view_id"] = database["view_id"]
        state["database_id"] = database["database_id"]
        assert state["database_id"], "Missing database ID"
        database_collab = read_page(state["database_view_id"], state["database_name"])
        state["database_sha256"] = hashlib.sha256(database_collab).hexdigest()
        record("create_read_database", passed=True, view_id=state["database_view_id"], database_id=state["database_id"])
        state["attachment_text"] = "Docker Swarm attachment byte equality " + state["marker"] + "\n"
        upload = request("PUT", f"/api/file_storage/{wid}/v1/blob/{state['document_id']}",
                         raw=state["attachment_text"].encode(), content_type="text/plain")
        state["attachment_id"] = upload["file_id"]
        save()
    else:
        state = json.loads(state_path.read_text())
        wid = state["workspace_id"]
        assert wid in [w["workspace_id"] for w in workspaces], "Persisted workspace missing"
        collab = read_page(state["document_id"], state["document_name"], state["marker"])
        # This fixture stays untouched; the browser tests use a separate document.
        assert hashlib.sha256(collab).hexdigest() == state["document_sha256"], "Stored document payload changed after replacement"
        record("persisted_document", passed=True, exact_bytes=True,
               sha256=state["document_sha256"])
        read_page(state["database_view_id"], state["database_name"])
        record("persisted_database", passed=True, database_id=state["database_id"])
    attachment_path = f"/api/file_storage/{wid}/v1/blob/{state['document_id']}/{urllib.parse.quote(state['attachment_id'], safe='')}"
    downloaded = request("GET", attachment_path, unwrap=False)
    assert downloaded == state["attachment_text"].encode(), "Attachment byte mismatch"
    record("attachment_upload_download" if args.phase == "create" else "persisted_attachment", passed=True,
           bytes=len(downloaded), sha256=hashlib.sha256(downloaded).hexdigest())
    if not args.skip_import and args.phase == "create":
        html = ("<!doctype html><html><body><h1>Docker Swarm Import</h1><p>Imported proof " + state["marker"] + "</p></body></html>").encode()
        imported = request("POST", f"/api/import/{wid}/document", payload={
            "content_length": len(html), "file_name": "swarm-proof.html", "format": "html",
            "parent_view_id": state["parent_id"], "name": "Swarm imported " + state["marker"]})
        state["import_task_id"] = imported["task_id"]
        save()
        request("PUT", imported["presigned_url"], raw=html, content_type="text/html", label="presigned_html_upload", unwrap=False, absolute=True)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            result = request("GET", f"/api/import/{wid}/document/{state['import_task_id']}")
            if str(result["status"]).lower() == "completed":
                state["import_view_id"] = result["view_id"]
                read_page(state["import_view_id"], marker=state["marker"])
                record("html_import_worker", passed=True, task_id=state["import_task_id"], view_id=state["import_view_id"])
                save()
                break
            if str(result["status"]).lower() == "failed":
                raise RuntimeError("HTML import failed: " + str(result.get("error")))
            time.sleep(3)
        else:
            raise AssertionError("HTML import did not complete before deadline")
    elif state.get("import_view_id"):
        read_page(state["import_view_id"], marker=state["marker"])
        record("persisted_imported_document", passed=True, view_id=state["import_view_id"])
    if not args.skip_search:
        verify_search()
    save()
    record("suite", passed=True, phase=args.phase)
except Exception as exc:
    record("suite", passed=False, phase=args.phase, error=redact(str(exc)))
    sys.exit(1)
finally:
    Path(str(state_path) + "." + args.phase + ".results.json").write_text(json.dumps(events, indent=2) + "\n")
