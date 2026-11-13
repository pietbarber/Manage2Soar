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
    assert "EMAIL_DEV_MODE = os.getenv(" in rendered_settings
    assert "EMAIL_DEV_MODE_REDIRECT_TO = os.getenv(" in rendered_settings


def test_rendered_axes_cleanup_timer_and_service():
    """The single-host role ships an hourly django-axes cleanup timer +
    oneshot service that run the cleanup command as the app user (issue
    #1110).  Verify the rendered units are coherent: the timer points at the
    service, the service runs the command via the virtualenv Python (NOT the
    manage.sh wrapper, which would shell-expand unquoted secrets), and both
    run as the unprivileged application user.
    """
    template_dir = Path(__file__).parents[1] / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir), autoescape=select_autoescape()
    )
    ctx = {
        "m2s_app_home": "/opt/m2s",
        "m2s_venv_path": "/opt/m2s/venv",
        "m2s_app_user": "m2s",
        "m2s_app_group": "m2s",
        "m2s_log_dir": "/var/log/m2s",
    }

    timer = env.get_template("m2s-cleanup-login-attempts.timer.j2").render(**ctx)
    service = env.get_template("m2s-cleanup-login-attempts.service.j2").render(**ctx)

    # Timer targets the oneshot service and is enabled on boot.
    assert "Unit=m2s-cleanup-login-attempts.service" in timer
    # Hourly schedule mirroring the K8s CronJob (minute 0 of every hour).
    assert "OnCalendar=*-*-* *:00:00 UTC" in timer
    assert "WantedBy=timers.target" in timer

    # Service runs the cleanup command as the app user, invoking the virtualenv
    # Python directly (NOT the manage.sh wrapper, which would shell-source the
    # env file and mangle unquoted secrets like DB_PASSWORD).
    assert "User=m2s" in service
    assert "Type=oneshot" in service
    assert (
        "/opt/m2s/venv/bin/python /opt/m2s/app/manage.py "
        "cleanup_login_attempts --verbosity=1" in service
    )
    # It must load the env via systemd's EnvironmentFile (literal, no shell
    # expansion) and the ExecStart line must NOT shell-source the file through
    # manage.sh (comments may mention manage.sh, so check the ExecStart line).
    assert "EnvironmentFile=/opt/m2s/app/.env" in service
    exec_start = next(
        line for line in service.splitlines() if line.startswith("ExecStart=")
    )
    assert "manage.sh" not in exec_start
    assert "WorkingDirectory=/opt/m2s/app" in service


def test_tasks_reconcile_disabled_timer():
    """When ``m2s_cleanup_login_attempts_enabled`` is false, the role must
    stop and disable the previously installed timer (and tolerate a missing
    unit), not just skip the enable tasks (issue #1110 review).
    """
    import yaml

    tasks_file = Path(__file__).parents[1] / "tasks" / "main.yml"
    tasks = yaml.safe_load(tasks_file.read_text())

    names = [t["name"] for t in tasks if isinstance(t, dict) and "name" in t]

    # The enable path.
    assert "Enable and start django-axes cleanup timer" in names

    # The opt-out path: stat the unit (tolerating absence) and stop+disable it
    # only when it exists.
    assert "Check if django-axes cleanup timer is installed" in names
    assert "Stop and disable django-axes cleanup timer when disabled" in names

    # The stop/disable task must be gated on both the flag being false AND the
    # unit existing, so it tolerates hosts where it was never installed.
    stop_task = next(
        t
        for t in tasks
        if isinstance(t, dict)
        and t.get("name") == "Stop and disable django-axes cleanup timer when disabled"
    )
    when = stop_task["when"]
    assert "not (m2s_cleanup_login_attempts_enabled | bool)" in when
    assert "m2s_cleanup_timer_present.stat.exists" in when
    # And it must set state to stopped + enabled false.
    assert stop_task["ansible.builtin.systemd"]["state"] == "stopped"
    assert stop_task["ansible.builtin.systemd"]["enabled"] is False
