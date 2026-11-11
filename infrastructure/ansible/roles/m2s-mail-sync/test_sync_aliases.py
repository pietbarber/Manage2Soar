"""Test admin forwarding aliases in the generated mail sync script."""

import os
import stat
import tempfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

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

    production = sync.generate_virtual_aliases({"club.org": club})
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
        }
    )
    assert "admin-@club.org  sales+@example.com" in content
    assert "admin--bounces@club.org  admin@example.com" in content


def test_dev_mode_redirects_to_multiple_addresses():
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
            "redirect_to": "first@example.com, second@example.com",
        },
    )
    assert "test@club.org  first@example.com,second@example.com" in content
    assert "admin@club.org  first@example.com,second@example.com" in content


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

    with patch.object(sync.subprocess, "run") as run:
        assert sync.write_and_postmap(str(virtual_file), "admin@example.com\n")

    assert stat.S_IMODE(os.stat(virtual_file).st_mode) == 0o644
    run.assert_called_once()
