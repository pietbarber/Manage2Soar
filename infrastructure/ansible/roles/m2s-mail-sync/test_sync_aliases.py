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

    with patch.object(
        sync.subprocess, "run", side_effect=fake_postmap
    ) as run, patch.object(
        sync.grp, "getgrnam", return_value=type("Group", (), {"gr_gid": os.getgid()})()
    ), patch.object(
        sync.os, "chown"
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

    def fake_replace(source, target):
        if target == str(virtual_file):
            raise OSError("source publication failed")
        return real_replace(source, target)

    def fake_postmap(command, check):
        Path(f"{command[1]}.db").write_text("new database")

    with patch.object(sync.subprocess, "run", side_effect=fake_postmap), patch.object(
        sync.grp, "getgrnam", return_value=type("Group", (), {"gr_gid": os.getgid()})()
    ), patch.object(sync.os, "chown"), patch.object(
        sync.os, "replace", side_effect=fake_replace
    ):
        with pytest.raises(OSError, match="source publication failed"):
            sync.write_and_postmap(str(virtual_file), "new source")

    assert virtual_file.read_text() == "old source"
    assert database_file.read_text() == "old database"


def test_virtual_map_keeps_live_database_during_publication(tmp_path):
    sync = load_sync_module()
    sync.MAP_LOCK_FILE = str(tmp_path / "map.lock")
    Path(sync.MAP_LOCK_FILE).touch()
    virtual_file = tmp_path / "virtual"
    virtual_file.write_text("old source")
    database_file = tmp_path / "virtual.db"
    database_file.write_text("old database")
    real_replace = os.replace

    def observe_replace(source, target):
        if target == str(database_file):
            assert database_file.read_text() == "old database"
        return real_replace(source, target)

    def fake_postmap(command, check):
        Path(f"{command[1]}.db").write_text("new database")

    with patch.object(sync.subprocess, "run", side_effect=fake_postmap), patch.object(
        sync.grp, "getgrnam", return_value=type("Group", (), {"gr_gid": os.getgid()})()
    ), patch.object(sync.os, "chown"), patch.object(
        sync.os, "replace", side_effect=observe_replace
    ):
        assert sync.write_and_postmap(str(virtual_file), "new source")

    assert virtual_file.read_text() == "new source"
    assert database_file.read_text() == "new database"


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


def test_protected_rspamd_map_includes_bypass_lists_for_spf():
    sync = load_sync_module()
    content = sync.generate_protected_lists_map(
        {"club.example.org": {"lists": {"board": [], "webmaster": []}}}
    )
    assert r"/^board(?:\+[^@]+)?@club\.example\.org$/i" in content
    assert r"/^webmaster(?:\+[^@]+)?@club\.example\.org$/i" in content


def test_bypass_rspamd_map_matches_tagged_recipients():
    sync = load_sync_module()
    content = sync.generate_bypass_lists_map(
        {"club": {"domains": ["club.example.org"], "bypass_lists": ["webmaster"]}}
    )
    assert r"/^webmaster(?:\+[^@]+)?@club\.example\.org$/i" in content


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
