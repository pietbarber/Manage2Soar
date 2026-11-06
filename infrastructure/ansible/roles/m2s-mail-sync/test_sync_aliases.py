"""Test admin forwarding aliases in the generated mail sync script."""

import tempfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from jinja2 import Template


def load_sync_module():
    template = Path(__file__).parent / "templates" / "sync-aliases.py.j2"
    source = Template(template.read_text()).render()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp:
        temp.write(source)
        path = Path(temp.name)
    try:
        spec = spec_from_file_location("sync_aliases_under_test", path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        path.unlink(missing_ok=True)


def test_forwarding_aliases_appear_after_lists_and_respect_dev_mode():
    sync = load_sync_module()
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
    assert "admin-bounces@club.org" not in content
    assert content.index("test@club.org") < content.index(
        "# --- Administrative forwarding aliases ---"
    )
    assert "external@example.com" not in content

    production = sync.generate_virtual_aliases({"club.org": club})
    assert "admin@club.org  external@example.com" in production
    assert "admin-bounces@club.org" not in production
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
