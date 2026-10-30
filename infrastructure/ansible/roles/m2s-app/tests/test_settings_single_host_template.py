"""Drift guard for the rendered single-host settings module.

The m2s-app role still renders ``settings_single_host.py.j2`` over the
checked-in module, so the two files must stay identical after rendering.  The
comparison ignores comments and the module docstring, which intentionally
differ, and compares the parsed Python body instead.
"""

import ast
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

ROLE_DIR = Path(__file__).parents[1]
REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "manage.py").exists()
)
TEMPLATE_DIR = ROLE_DIR / "templates"
TEMPLATE = TEMPLATE_DIR / "settings_single_host.py.j2"
CHECKED_IN_SETTINGS = REPO_ROOT / "manage2soar" / "settings_single_host.py"
ROLE_DEFAULTS = ROLE_DIR / "defaults" / "main.yml"


def _role_default_import_export_tmp_dir() -> str:
    """Resolve the role default instead of duplicating its path here."""
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))
    return Template(defaults["m2s_import_export_tmp_dir"]).render(**defaults)


def _render_template() -> str:
    template = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape()
    ).get_template("settings_single_host.py.j2")
    return template.render(
        m2s_import_export_tmp_dir=_role_default_import_export_tmp_dir()
    )


def _executable_body(source: str):
    """Return top-level statements without the leading module docstring."""
    body = list(ast.parse(source).body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return [ast.dump(node, include_attributes=False) for node in body]


def test_rendered_template_matches_checked_in_settings():
    rendered = _render_template()
    checked_in = CHECKED_IN_SETTINGS.read_text(encoding="utf-8")

    assert _executable_body(rendered) == _executable_body(checked_in), (
        "settings_single_host.py.j2 is out of sync with "
        "manage2soar/settings_single_host.py; update both files together"
    )


def test_template_uses_the_deployment_import_export_variable():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "{{ m2s_import_export_tmp_dir }}" in source


def test_rendered_single_host_settings_protect_social_auth_user_fields():
    settings_tree = ast.parse(_render_template())
    protected_fields_assignment = next(
        node
        for node in settings_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "SOCIAL_AUTH_PROTECTED_USER_FIELDS"
            for target in node.targets
        )
    )

    assert ast.literal_eval(protected_fields_assignment.value) == [
        "first_name",
        "last_name",
        "email",
    ]
