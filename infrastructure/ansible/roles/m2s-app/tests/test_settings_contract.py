"""Structural drift guards for single-host settings and deployment config.

The checked-in ``manage2soar/settings_single_host.py`` is the authoritative
module for developers and tests.  The m2s-app role still renders
``settings_single_host.py.j2`` over it on single-host hosts, so the template
must stay in sync; ``test_settings_single_host_template.py`` enforces that.

These are structural checks (presence, literals, and parsed bodies), not proof
of runtime equivalence.  Environment values, conditional branches, and helper
behavior still require deployment smoke testing.
"""

import ast
import re
from pathlib import Path

from manage2soar.settings_env import is_test_settings_module, is_testing

ROLE_DIR = Path(__file__).parents[1]
REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "manage.py").exists()
)
BASE_SETTINGS = REPO_ROOT / "manage2soar" / "settings.py"
SINGLE_HOST_SETTINGS = REPO_ROOT / "manage2soar" / "settings_single_host.py"
ENV_TEMPLATE = ROLE_DIR / "templates" / "env.j2"
ROLE_DEFAULTS = ROLE_DIR / "defaults" / "main.yml"
ROLE_TASKS = ROLE_DIR / "tasks" / "main.yml"

SHARED_SECURITY_CONTRACT = {
    "AUTHENTICATION_BACKENDS",
    "CSRF_COOKIE_SAMESITE",
    "CSRF_TRUSTED_ORIGINS",
    "EMAIL_DEV_MODE",
    "KIOSK_COOKIE_SECURE",
    "MIDDLEWARE",
    "SECURE_HSTS_SECONDS",
    "SESSION_COOKIE_SAMESITE",
    "SOCIAL_AUTH_PROTECTED_USER_FIELDS",
    "TINYMCE_JS_URL",
}

REQUIRED_DEPLOYMENT_ENV = {
    "ALLOWED_HOSTS",
    "CLUB_PREFIX",
    "DB_HOST",
    "DB_NAME",
    "DB_PASSWORD",
    "DB_PORT",
    "DB_USER",
    "DJANGO_DEBUG",
    "DJANGO_SECRET_KEY",
    "DJANGO_SETTINGS_MODULE",
    "IMPORT_EXPORT_TMP_DIR",
    "MEDIA_ROOT",
    "SITE_URL",
    "STATIC_ROOT",
}


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _assigned_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _module_literal(tree, name):
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a module-level literal assignment")


def test_ansible_role_deploys_the_single_host_settings_template():
    assert (ROLE_DIR / "templates" / "settings_single_host.py.j2").exists()
    tasks = ROLE_TASKS.read_text(encoding="utf-8")
    assert "src: settings_single_host.py.j2" in tasks
    assert 'dest: "{{ m2s_app_home }}/app/manage2soar/settings_single_host.py"' in tasks


def test_ansible_uses_the_checked_in_settings_module():
    defaults = ROLE_DEFAULTS.read_text(encoding="utf-8")
    assert re.search(
        r'^m2s_django_settings_module:\s*"manage2soar\.settings_single_host"$',
        defaults,
        re.MULTILINE,
    )


def test_single_host_settings_include_security_and_kiosk_contract():
    tree = _tree(SINGLE_HOST_SETTINGS)
    names = _assigned_names(tree)

    assert {"KIOSK_COOKIE_SECURE", "IMPORT_EXPORT_TMP_DIR"} <= names
    assert "members.auth_backends.QualificationPermissionBackend" in (
        _module_literal(tree, "AUTHENTICATION_BACKENDS")
    )
    assert "utils.middleware.KioskAutoLoginMiddleware" in _module_literal(
        tree, "MIDDLEWARE"
    )


def test_base_and_single_host_share_the_security_contract():
    base_tree = _tree(BASE_SETTINGS)
    single_tree = _tree(SINGLE_HOST_SETTINGS)

    assert SHARED_SECURITY_CONTRACT <= _assigned_names(base_tree)
    assert SHARED_SECURITY_CONTRACT <= _assigned_names(single_tree)
    assert "members.auth_backends.QualificationPermissionBackend" in (
        _module_literal(base_tree, "AUTHENTICATION_BACKENDS")
    )
    assert "utils.middleware.KioskAutoLoginMiddleware" in _module_literal(
        base_tree, "MIDDLEWARE"
    )
    assert _module_literal(base_tree, "SOCIAL_AUTH_PROTECTED_USER_FIELDS") == (
        _module_literal(single_tree, "SOCIAL_AUTH_PROTECTED_USER_FIELDS")
    )


def test_single_host_debug_is_not_derived_from_test_detection():
    tree = _tree(SINGLE_HOST_SETTINGS)
    debug_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEBUG"
            for target in node.targets
        )
    )
    assert "TESTING" not in ast.unparse(debug_assignment.value)


def test_deployment_template_supplies_required_environment():
    env_template = ENV_TEMPLATE.read_text(encoding="utf-8")
    missing = {
        key
        for key in REQUIRED_DEPLOYMENT_ENV
        if not re.search(rf"^{re.escape(key)}=", env_template, re.MULTILINE)
    }
    assert not missing, f"env.j2 is missing: {', '.join(sorted(missing))}"


def test_settings_module_detection_requires_a_name_token():
    assert is_test_settings_module("roles_permissions_postgres_test_settings")
    assert is_test_settings_module("manage2soar.settings_test")
    assert is_test_settings_module("manage2soar.test_settings")
    assert not is_test_settings_module("manage2soar.latest_settings")
    assert not is_test_settings_module("manage2soar.settings_single_host")


def test_test_detection_requires_a_runner_or_test_subcommand():
    module = "manage2soar.settings_single_host"
    assert not is_testing(
        settings_module=module, argv=["manage.py", "loaddata", "test"], modules={}
    )
    assert not is_testing(
        settings_module=module, argv=["manage.py", "loaddata", "latest"], modules={}
    )
    assert is_testing(settings_module=module, argv=["manage.py", "test"], modules={})
    assert is_testing(settings_module=module, argv=["/usr/bin/pytest"], modules={})
    assert is_testing(
        settings_module="manage2soar.settings_test",
        argv=["manage.py", "runserver"],
        modules={},
    )
