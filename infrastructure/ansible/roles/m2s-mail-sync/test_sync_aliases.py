"""Test admin forwarding aliases in the generated mail sync script."""

import os
import stat
import tempfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

import pytest
from jinja2 import Template


def load_sync_module(**context):
    template = Path(__file__).parent / "templates" / "sync-aliases.py.j2"
    source = Template(template.read_text()).render(**context)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp:
        temp.write(source)
        path = Path(temp.name)
    try:
        spec = spec_from_file_location("sync_aliases_under_test", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load generated sync script: {path}")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        path.unlink(missing_ok=True)


def test_forwarding_aliases_appear_after_lists_and_respect_dev_mode():
    sync = load_sync_module(admin_email="admin@example.com")
    club = {
        "lists": {"test": ["member@example.com"]},
        "forwarding_aliases": {"admin": "external@example.com"},
    }
    content = sync.generate_virtual_aliases(
        {"club.org": club},
        dev_mode={"enabled": True, "redirect_to": "preview@gmail.com"},
    )
    assert "test@club.org  preview@gmail.com" in content
    assert "admin@club.org  preview@gmail.com" in content
    assert "admin-bounces@club.org  preview@gmail.com" in content
    assert content.index("test@club.org") < content.index(
        "# --- Administrative forwarding aliases ---"
    )
    assert "external@example.com" not in content

    production = sync.generate_virtual_aliases(
        {"club.org": club}, bounce_email="admin@example.com"
    )
    assert "admin@club.org  external@example.com" in production
    assert "admin-bounces@club.org  admin@example.com" in production
    assert "test@club.org  member@example.com" in production


def test_rejects_invalid_forwarding_alias_data():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {},
                "forwarding_aliases": {"bad name": "external@example.com"},
            }
        }
    )
    assert "bad name@club.org" not in content


def test_forwarding_addresses_allow_trailing_plus_or_hyphen():
    sync = load_sync_module(admin_email="admin@example.com")
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {},
                "forwarding_aliases": {"admin-": "sales+@example.com"},
            }
        },
        bounce_email="admin@example.com",
    )
    assert "admin-@club.org  sales+@example.com" in content
    assert "admin--bounces@club.org  admin@example.com" in content


def test_rejects_invalid_mailing_list_names_before_map_generation():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {
                    "bad\nadmin": ["member@example.com"],
                    "admin-": ["member@example.com"],
                },
            }
        }
    )
    assert "bad\nadmin@club.org" not in content
    assert "admin-@club.org  member@example.com" in content


def test_dev_mode_supports_multiple_redirect_recipients():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {"test": ["member@example.com"]},
                "forwarding_aliases": {"admin": "external@example.com"},
            }
        },
        dev_mode={
            "enabled": True,
            "redirect_to": "one@example.com, two@example.com",
        },
    )
    assert "test@club.org  one@example.com,two@example.com" in content
    assert "admin@club.org  one@example.com,two@example.com" in content


def test_forwarding_to_legacy_local_domain_is_rejected():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "ysc.manage2soar.com": {
                "lists": {},
                "forwarding_aliases": {
                    "admin": "user@ysc.manage2soar.com",
                },
            }
        },
        local_domains={"ysc.manage2soar.com"},
    )
    assert "admin@ysc.manage2soar.com  user@ysc.manage2soar.com" not in content


def test_virtual_map_publish_is_readable_by_rewriter(tmp_path):
    sync = load_sync_module()
    virtual_file = tmp_path / "virtual"
    sync.MAP_LOCK_FILE = str(tmp_path / "map.lock")
    Path(sync.MAP_LOCK_FILE).touch()

    def fake_postmap(command, check):
        Path(f"{command[1]}.db").write_text("database")

    with (
        patch.object(sync.subprocess, "run", side_effect=fake_postmap) as run,
        patch.object(
            sync.grp,
            "getgrnam",
            return_value=type("Group", (), {"gr_gid": os.getgid()})(),
        ),
        patch.object(sync.os, "chown"),
    ):
        assert sync.write_and_postmap(str(virtual_file), "admin@example.com\n")

    assert stat.S_IMODE(os.stat(virtual_file).st_mode) == 0o640
    run.assert_called_once()


def test_virtual_map_restores_database_if_source_publish_fails(tmp_path):
    sync = load_sync_module()
    sync.MAP_LOCK_FILE = str(tmp_path / "map.lock")
    Path(sync.MAP_LOCK_FILE).touch()
    virtual_file = tmp_path / "virtual"
    virtual_file.write_text("old source")
    database_file = tmp_path / "virtual.db"
    database_file.write_text("old database")
    real_replace = os.replace
    source_publish_attempts = 0

    def fake_replace(source, target):
        nonlocal source_publish_attempts
        if target == str(virtual_file):
            source_publish_attempts += 1
            if source_publish_attempts == 1:
                raise OSError("source publication failed")
        return real_replace(source, target)

    def fake_postmap(command, check):
        Path(f"{command[1]}.db").write_text("new database")

    with (
        patch.object(sync.subprocess, "run", side_effect=fake_postmap),
        patch.object(
            sync.grp,
            "getgrnam",
            return_value=type("Group", (), {"gr_gid": os.getgid()})(),
        ),
        patch.object(sync.os, "chown"),
        patch.object(sync.os, "replace", side_effect=fake_replace),
    ):
        with pytest.raises(OSError, match="source publication failed"):
            sync.write_and_postmap(str(virtual_file), "new source")

    assert virtual_file.read_text() == "old source"
    assert database_file.read_text() == "old database"


def test_virtual_map_publishes_database_before_source_under_lock(tmp_path):
    sync = load_sync_module()
    sync.MAP_LOCK_FILE = str(tmp_path / "map.lock")
    Path(sync.MAP_LOCK_FILE).touch()
    virtual_file = tmp_path / "virtual"
    database_file = tmp_path / "virtual.db"
    virtual_file.write_text("old source")
    database_file.write_text("old database")
    order = []
    real_replace = os.replace

    def fake_replace(source, target):
        if target == str(database_file):
            order.append("database")
        elif target == str(virtual_file):
            order.append("source")
        return real_replace(source, target)

    def fake_postmap(command, check):
        Path(f"{command[1]}.db").write_text("new database")

    with (
        patch.object(sync.subprocess, "run", side_effect=fake_postmap),
        patch.object(
            sync.grp,
            "getgrnam",
            return_value=type("Group", (), {"gr_gid": os.getgid()})(),
        ),
        patch.object(sync.os, "chown"),
        patch.object(sync.os, "replace", side_effect=fake_replace),
    ):
        assert sync.write_and_postmap(str(virtual_file), "new source")

    assert order == ["database", "source"]


def test_virtual_map_removes_new_database_if_source_publish_fails_without_old_db(
    tmp_path,
):
    sync = load_sync_module()
    sync.MAP_LOCK_FILE = str(tmp_path / "map.lock")
    Path(sync.MAP_LOCK_FILE).touch()
    virtual_file = tmp_path / "virtual"
    real_replace = os.replace

    def fake_replace(source, target):
        if target == str(virtual_file):
            raise OSError("source publication failed")
        return real_replace(source, target)

    def fake_postmap(command, check):
        Path(f"{command[1]}.db").write_text("new database")

    with (
        patch.object(sync.subprocess, "run", side_effect=fake_postmap),
        patch.object(
            sync.grp,
            "getgrnam",
            return_value=type("Group", (), {"gr_gid": os.getgid()})(),
        ),
        patch.object(sync.os, "chown"),
        patch.object(sync.os, "replace", side_effect=fake_replace),
    ):
        with pytest.raises(OSError, match="source publication failed"):
            sync.write_and_postmap(str(virtual_file), "new source")

    assert not virtual_file.exists()
    assert not Path(f"{virtual_file}.db").exists()


def test_map_transaction_recovers_source_and_database_as_one_generation(tmp_path):
    sync = load_sync_module()
    source = tmp_path / "virtual"
    database = tmp_path / "virtual.db"
    source.write_text("old source")
    database.write_text("old database")
    source_backup = tmp_path / "source.backup"
    database_backup = tmp_path / "database.backup"
    source_backup.write_text(source.read_text())
    database_backup.write_text(database.read_text())
    source.write_text("new source")
    database.write_text("new database")
    transaction = {
        "filepath": str(source),
        "files": [
            {"target": str(source), "backup": str(source_backup), "existed": True},
            {"target": str(database), "backup": str(database_backup), "existed": True},
        ],
    }
    (tmp_path / "virtual.transaction").write_text(__import__("json").dumps(transaction))

    assert sync.recover_map_transaction(str(source)) is True
    assert source.read_text() == "old source"
    assert database.read_text() == "old database"
    assert not (tmp_path / "virtual.transaction").exists()
    assert not source_backup.exists()
    assert not database_backup.exists()


def test_rewriter_refuses_to_read_during_pending_map_recovery(tmp_path):
    postfix_template = (
        Path(__file__).parents[1] / "postfix" / "templates" / "maillist-rewriter.py.j2"
    )
    source = Template(postfix_template.read_text()).render(
        club_domains=[{"prefix": "club"}], mail_domain="example.com"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp:
        temp.write(source)
        path = Path(temp.name)
    try:
        spec = spec_from_file_location("rewriter_under_test", path)
        assert spec is not None and spec.loader is not None
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        virtual_file = tmp_path / "virtual"
        virtual_file.write_text("members@example.com  member@example.net\n")
        (tmp_path / "virtual.transaction").write_text("pending")
        module.MAP_LOCK_FILE = str(tmp_path / "map.lock")
        Path(module.MAP_LOCK_FILE).touch()

        assert module._load_routing_snapshot(str(virtual_file)) == (set(), set(), {})
    finally:
        path.unlink(missing_ok=True)


def test_broad_sync_tags_do_not_select_prerequisite_roles():
    root = Path(__file__).parents[2] / "playbooks"
    for filename in ("single-host.yml", "mail-server.yml", "gcp-mail-server.yml"):
        content = (root / filename).read_text()
        assert "tags: [postgresql, database, sync]" not in content
        assert "tags: [app, application, sync]" not in content
        assert "tags: [postfix, mail, sync]" not in content
        assert "tags: [postfix, mail, mail-sync]" not in content
        assert "tags: [opendkim, dkim, mail, sync]" not in content
        assert "tags: [opendkim, dkim, mail, mail-sync]" not in content
        assert "tags: [rspamd, spam, mail, sync]" not in content
        assert "tags: [rspamd, spam, mail, mail-sync]" not in content


def test_fetch_rejects_any_http_redirect_without_following():
    sync = load_sync_module()
    response = type("Response", (), {"status_code": 302})()
    with patch.object(sync.requests, "get", return_value=response) as request:
        assert (
            sync.fetch_club_lists(
                {"prefix": "club", "api_url": "https://club.example/api"}, "secret"
            )
            is None
        )
    request.assert_called_once_with(
        "https://club.example/api",
        headers={"X-API-Key": "secret", "Accept": "application/json"},
        timeout=30,
        allow_redirects=False,
    )


def test_spf_maps_match_bare_plus_recipient_delimiter():
    sync = load_sync_module()
    content = sync.generate_protected_lists_map(
        {"club.example.org": {"lists": {"board": []}}}
    )
    pattern = r"/^board(?:\+[^@]*)?@club\.example\.org$/i"
    assert pattern in content
    import re

    assert re.search(
        r"^board(?:\+[^@]*)?@club\.example\.org$", "board+@club.example.org", re.I
    )


def test_forwarding_alias_rejects_legacy_local_domain():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {},
                "forwarding_aliases": {"admin": "admin@club.legacy.org"},
            }
        },
        local_domains={"club.legacy.org"},
    )
    assert "admin@club.org" not in content


def test_redirect_parser_rejects_empty_entries():
    sync = load_sync_module()
    assert sync.parse_redirect_recipients("one@example.com,") == []
    assert sync.parse_redirect_recipients("one@example.com,,two@example.com") == []


def test_postfix_recipient_checks_use_tenant_scoped_classes():
    sync = load_sync_module()
    content = sync.generate_recipient_whitelist_check(
        {
            "ssc.example.org": {"lists": {"board": ["ssc@example.com"]}},
            "masa.example.org": {"lists": {"board": ["masa@example.com"]}},
        },
        {},
        {
            "ssc": {"domains": ["ssc.example.org"], "whitelist": ["ssc@example.com"]},
            "masa": {
                "domains": ["masa.example.org"],
                "whitelist": ["masa@example.com"],
            },
        },
    )
    assert "board@ssc.example.org  whitelist_required_ssc" in content
    assert "board@masa.example.org  whitelist_required_masa" in content


def test_api_url_requires_https_except_local_development():
    sync = load_sync_module()
    assert sync.is_safe_api_url("https://club.example/api/email-lists/")
    assert sync.is_safe_api_url("http://127.0.0.1:8000/api/email-lists/")
    assert not sync.is_safe_api_url("http://club.example/api/email-lists/")


def test_api_response_schema_rejects_malformed_authorization_data():
    sync = load_sync_module()
    with pytest.raises(ValueError):
        sync.validate_club_response({"lists": []})
    with pytest.raises(ValueError):
        sync.validate_club_response({"lists": {"board": ["member@example.com", None]}})


def test_configuration_rejects_duplicate_tenant_domains_and_prefixes():
    sync = load_sync_module()
    base_club = {
        "prefix": "one",
        "domains": ["shared.example.org"],
        "api_url": "https://one.example.org/api/email-lists/",
    }
    duplicate_domain = {
        "mail_domain": "example.org",
        "clubs": [
            base_club,
            {
                "prefix": "two",
                "domains": ["SHARED.example.org"],
                "api_url": "https://two.example.org/api/email-lists/",
            },
        ],
    }
    with pytest.raises(ValueError, match="assigned more than once"):
        sync.validate_configuration(duplicate_domain)

    duplicate_prefix = {
        "mail_domain": "example.org",
        "clubs": [base_club, {**base_club, "domains": ["two.example.org"]}],
    }
    with pytest.raises(ValueError, match="duplicate tenant prefix"):
        sync.validate_configuration(duplicate_prefix)


def test_ansible_uniqueness_checks_preserve_duplicates_until_assertion():
    mail_sync_tasks = (Path(__file__).parent / "tasks" / "main.yml").read_text()
    postfix_tasks = (
        Path(__file__).parent.parent / "postfix" / "tasks" / "main.yml"
    ).read_text()

    assert "m2s_mail_sync_resolved_tenant_domains: []" in mail_sync_tasks
    assert "postfix_resolved_tenant_domains: []" in postfix_tasks
    assert (
        "m2s_mail_sync_resolved_tenant_domains + (_tenant_domains | map('lower') | list)"
        in mail_sync_tasks
    )
    assert (
        "postfix_resolved_tenant_domains + (_tenant_domains | map('lower') | list)"
        in postfix_tasks
    )


def test_guarded_maps_retain_old_authorization_until_routing_is_live(tmp_path):
    sync = load_sync_module()
    recipient_map = tmp_path / "recipient_whitelist_check"
    recipient_map.write_text(
        "old@example.org  whitelist_required_old\n"
        "same@example.org  whitelist_required_old\n"
    )
    guarded = sync.guarded_postfix_map(
        str(recipient_map),
        "same@example.org  whitelist_required_new\n"
        "new@example.org  whitelist_required_new\n",
    )
    assert "old@example.org  whitelist_required_old" in guarded
    assert "same@example.org  whitelist_required_new" in guarded
    assert "same@example.org  whitelist_required_old" not in guarded

    protected_map = tmp_path / "protected_lists.map"
    protected_map.write_text("/^old@example\\.org$/i\n")
    guarded_protected = sync.guarded_rspamd_map(
        str(protected_map), "/^new@example\\.org$/i\n"
    )
    assert "/^old@example\\.org$/i" in guarded_protected
    assert "/^new@example\\.org$/i" in guarded_protected


def test_rspamd_map_write_failure_is_fatal(tmp_path):
    sync = load_sync_module()
    missing_path = tmp_path / "missing" / "protected_lists.map"
    with pytest.raises(FileNotFoundError, match="directory does not exist"):
        sync.write_rspamd_whitelist(str(missing_path), "protected\n")


def test_main_publishes_authorization_before_routing_and_finalizes_afterward():
    sync = load_sync_module()
    config = {
        "mail_domain": "example.org",
        "mail_hostname": "mail.example.org",
        "admin_email": "monitor@example.net",
        "default_auth_token": "secret",
        "postfix_virtual_file": "/maps/virtual",
        "postfix_whitelist_dir": "/maps/tenant-whitelists",
        "postfix_recipient_check_file": "/maps/recipient_whitelist_check",
        "clubs": [
            {
                "prefix": "club",
                "domains": ["club.example.org"],
                "api_url": "https://club.example.org/api/email-lists/",
            }
        ],
    }
    writes = []

    def record_write(path, content):
        writes.append(path)
        return True

    with (
        patch.object(sync, "load_config", return_value=config),
        patch.object(
            sync,
            "fetch_club_lists",
            return_value={
                "lists": {"board": ["member@example.net"]},
                "whitelist": ["member@example.net"],
            },
        ),
        patch.object(sync, "write_and_postmap", side_effect=record_write),
    ):
        sync.main()

    recipient_path = config["postfix_recipient_check_file"]
    virtual_path = config["postfix_virtual_file"]
    assert writes.index(recipient_path) < writes.index(virtual_path)
    assert writes.index(virtual_path) < len(writes) - 1
    assert writes[-1] == recipient_path


def test_routing_failure_leaves_guarded_authorization_in_place(tmp_path):
    sync = load_sync_module()
    recipient_path = tmp_path / "recipient_whitelist_check"
    recipient_path.write_text("old@club.example.org  whitelist_required_club\n")
    config = {
        "mail_domain": "example.org",
        "mail_hostname": "mail.example.org",
        "admin_email": "monitor@example.net",
        "default_auth_token": "secret",
        "postfix_virtual_file": str(tmp_path / "virtual"),
        "postfix_whitelist_dir": str(tmp_path / "tenant-whitelists"),
        "postfix_recipient_check_file": str(recipient_path),
        "clubs": [
            {
                "prefix": "club",
                "domains": ["club.example.org"],
                "api_url": "https://club.example.org/api/email-lists/",
            }
        ],
    }
    writes = []

    def fail_on_routing(path, content):
        writes.append((path, content))
        if path == config["postfix_virtual_file"]:
            raise OSError("routing publication failed")
        return True

    with (
        patch.object(sync, "load_config", return_value=config),
        patch.object(
            sync,
            "fetch_club_lists",
            return_value={
                "lists": {"board": ["member@example.net"]},
                "whitelist": ["member@example.net"],
            },
        ),
        patch.object(sync, "write_and_postmap", side_effect=fail_on_routing),
        pytest.raises(OSError, match="routing publication failed"),
    ):
        sync.main()

    recipient_writes = [
        content for path, content in writes if path == str(recipient_path)
    ]
    assert len(recipient_writes) == 1
    assert "old@club.example.org  whitelist_required_club" in recipient_writes[0]


def test_total_api_outage_preserves_routes_and_exits_nonzero():
    sync = load_sync_module()
    config = {
        "mail_domain": "example.org",
        "default_auth_token": "secret",
        "postfix_virtual_file": "/maps/virtual",
        "postfix_whitelist_dir": "/maps/tenant-whitelists",
        "postfix_recipient_check_file": "/maps/recipient_whitelist_check",
        "clubs": [
            {
                "prefix": "club",
                "domains": ["club.example.org"],
                "api_url": "https://club.example.org/api/email-lists/",
            }
        ],
    }
    with (
        patch.object(sync, "load_config", return_value=config),
        patch.object(sync, "fetch_club_lists", return_value=None),
        patch.object(sync, "clear_virtual_aliases") as clear_routes,
        patch.object(sync, "clear_authorization_maps") as clear_authorization,
        pytest.raises(SystemExit) as exc,
    ):
        sync.main()

    assert exc.value.code == 1
    clear_routes.assert_not_called()
    clear_authorization.assert_not_called()


def test_protected_rspamd_map_includes_bypass_lists_for_spf():
    sync = load_sync_module()
    content = sync.generate_protected_lists_map(
        {"club.example.org": {"lists": {"board": [], "webmaster": []}}}
    )
    assert r"/^board(?:\+[^@]*)?@club\.example\.org$/i" in content
    assert r"/^webmaster(?:\+[^@]*)?@club\.example\.org$/i" in content


def test_bypass_rspamd_map_matches_tagged_recipients():
    sync = load_sync_module()
    content = sync.generate_bypass_lists_map(
        {"club": {"domains": ["club.example.org"], "bypass_lists": ["webmaster"]}}
    )
    assert r"/^webmaster(?:\+[^@]*)?@club\.example\.org$/i" in content


def test_forwarding_and_list_bounces_route_to_external_admin():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {"test": ["member@example.com"]},
                "forwarding_aliases": {"admin": "external@example.com"},
            }
        },
        bounce_email="postmaster@monitor.example",
    )
    assert "test-bounces@club.org  postmaster@monitor.example" in content
    assert "admin-bounces@club.org  postmaster@monitor.example" in content


def test_dev_mode_redirects_bounces_to_preview_recipients():
    sync = load_sync_module()
    content = sync.generate_virtual_aliases(
        {
            "club.org": {
                "lists": {"test": ["member@example.com"]},
                "forwarding_aliases": {"admin": "external@example.com"},
            }
        },
        dev_mode={"enabled": True, "redirect_to": "preview@example.com"},
        bounce_email="real-monitor@example.com",
    )
    assert "test-bounces@club.org  preview@example.com" in content
    assert "admin-bounces@club.org  preview@example.com" in content
    assert "real-monitor@example.com" not in content


def test_clear_virtual_aliases_sanitizes_reason_text():
    sync = load_sync_module()
    written = {}
    sync.write_and_postmap = lambda path, content: written.update(
        path=path, content=content
    )

    sync.clear_virtual_aliases(
        {"postfix_virtual_file": "/tmp/virtual"},
        "invalid redirect: bad\nadmin@club.org real@example.net\t\x00",
    )

    assert all(line.startswith("#") for line in written["content"].splitlines())
    assert "\nadmin@" not in written["content"]
    assert (
        "# Reason: invalid redirect: bad admin@club.org real@example.net"
        in written["content"]
    )
