#!/usr/bin/env python3
#########################################################
# generate_erds.py
#
# Generate .dot and .png ER diagrams for each Django app listed below.
# Run this from your project root (where manage.py lives) with your venv activated:
#
#     python generate_erds.py
#########################################################

import os
import subprocess
import sys

# Update this list if you add/remove apps
APPS = ["instructors", "members", "logsheet",
        "duty_roster", "knowledgetest", "analytics", "cms"]


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    python = sys.executable  # ensures we use the same venv python

    for app in APPS:
        docs_dir = os.path.join(project_root, app, "docs")
        os.makedirs(docs_dir, exist_ok=True)

        dot_path = os.path.join(docs_dir, f"{app}.dot")
        png_path = os.path.join(docs_dir, f"{app}.png")

        print(f"Generating {dot_path} …")
        subprocess.check_call([
            python, "manage.py", "graph_models", app,
            "--arrow-shape", "normal",
            "--group-models",    # group models by app
            "--output", dot_path
        ])

        print(f"Rendering {png_path} …")
        subprocess.check_call([
            "dot", "-Tpng", dot_path, "-o", png_path
        ])

    print("\nAll ERDs generated successfully!")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(
            f"\nError: command {e.cmd} failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
