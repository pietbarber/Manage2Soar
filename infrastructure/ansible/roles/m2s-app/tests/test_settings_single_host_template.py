import ast
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def test_rendered_single_host_settings_protect_social_auth_user_fields():
    template_dir = Path(__file__).parents[1] / "templates"
    template = Environment(
        loader=FileSystemLoader(template_dir), autoescape=select_autoescape()
    ).get_template("settings_single_host.py.j2")
    rendered_settings = template.render(
        m2s_import_export_tmp_dir="/var/tmp/manage2soar/import-export"
    )
    settings_tree = ast.parse(rendered_settings)
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
