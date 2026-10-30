## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
## Python environment

For all Python commands, use the local virtual environment explicitly:

- Run Python as `.venv/bin/python`
- Run tools as `.venv/bin/<tool>` (for example, `.venv/bin/pytest`)
- Never use the system Python or activate another environment unless requested.

## Pull requests
Always ask the user to check the branch, diff, and target repo before opening a PR on GitHub. Never create a PR without explicit confirmation.

## Deployment drift prevention

The GKE deployment is the default path and uses `manage2soar/settings.py`. Single-host is an explicit variant, not a replacement default. When changing shared behavior:

- Update `manage2soar/settings.py` and `manage2soar/settings_single_host.py` together.
- The m2s-app Ansible role also renders `infrastructure/ansible/roles/m2s-app/templates/settings_single_host.py.j2` over the single-host module. Update the template in the same change; `infrastructure/ansible/roles/m2s-app/tests/test_settings_single_host_template.py` fails when the rendered template and checked-in module diverge.
- If a new environment variable is required, add it to the relevant deployment template (`infrastructure/ansible/roles/m2s-app/templates/env.j2` for single-host, `infrastructure/ansible/roles/gke-deploy/templates/k8s-secrets.yml.j2` for GKE) or give the settings module a safe default. `test_settings_contract.py` guards the single-host side.
- Verify both settings modules with `manage.py check` and `makemigrations --check` before committing.
- Do not change the deployment model as a drive-by: artifact pinning, Python runtime, scheduled jobs, and CI topology are tracked as follow-ups, not folded into feature work.

## Other notes
Do not to do tests on everything try to keep it only to large changes and before commits
