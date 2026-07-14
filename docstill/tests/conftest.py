from pathlib import Path

from docstill.envfile import load_env_file

# Load engine credentials from docstill/.env for integration tests.
# Placeholder (REPLACE_ME) values never enter the environment.
load_env_file(Path(__file__).parent.parent / ".env")
