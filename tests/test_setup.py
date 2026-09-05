import json
import os
from pathlib import Path
from unittest.mock import patch

from onshape_mcp.config import _find_base_dir
from onshape_mcp.setup import (
    configure_claude_desktop,
    get_claude_desktop_config_path,
)


def test_find_base_dir_env_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom_dir"
    custom.mkdir()
    with patch.dict(os.environ, {"ONSHAPE_DIR": str(custom)}):
        assert _find_base_dir() == custom


def test_get_claude_desktop_config_path() -> None:
    p = get_claude_desktop_config_path()
    assert isinstance(p, Path)
    assert p.name == "claude_desktop_config.json"


def test_configure_claude_desktop_in_temp(tmp_path: Path) -> None:
    target_config = tmp_path / "claude_desktop_config.json"
    target_config.write_text(json.dumps({"existing_key": 123}), encoding="utf-8")

    with patch("onshape_mcp.setup.get_claude_desktop_config_path", return_value=target_config):
        res = configure_claude_desktop(doc_url="https://cad.onshape.com/test", auto_yes=True)
        assert res == target_config
        assert target_config.with_suffix(".json.bak").exists()

        data = json.loads(target_config.read_text(encoding="utf-8"))
        assert data["existing_key"] == 123
        assert "onshape" in data["mcpServers"]
        entry = data["mcpServers"]["onshape"]
        assert entry["command"] == "uvx"
        assert entry["env"]["ONSHAPE_DEFAULT_DOC"] == "https://cad.onshape.com/test"
