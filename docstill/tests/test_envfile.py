from docstill.envfile import load_env_file


def test_loads_real_values_skips_placeholders(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "REAL_KEY=abc123\n"
        "PLACEHOLDER_KEY=REPLACE_ME\n"
        "QUOTED_KEY='quoted'\n"
        "EMPTY_KEY=\n"
        "not a kv line\n"
    )
    for k in ("REAL_KEY", "PLACEHOLDER_KEY", "QUOTED_KEY", "EMPTY_KEY"):
        monkeypatch.delenv(k, raising=False)

    load_env_file(env)

    import os

    assert os.environ.get("REAL_KEY") == "abc123"
    assert "PLACEHOLDER_KEY" not in os.environ
    assert os.environ.get("QUOTED_KEY") == "quoted"
    assert "EMPTY_KEY" not in os.environ
    monkeypatch.delenv("REAL_KEY")
    monkeypatch.delenv("QUOTED_KEY")


def test_existing_env_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("MY_KEY=from_file\n")
    monkeypatch.setenv("MY_KEY", "from_shell")
    load_env_file(env)
    import os

    assert os.environ["MY_KEY"] == "from_shell"


def test_missing_file_is_noop(tmp_path):
    load_env_file(tmp_path / "does-not-exist.env")  # must not raise
