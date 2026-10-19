"""API process must resolve scholar_mcp without relying on a lucky cwd."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from scholarflow_api.config import ensure_scholar_mcp_on_path, repo_root
from scholarflow_api.graph import adapters


def _drop_scholar_mcp_from_path_and_modules() -> Path:
    mcp_root = repo_root() / "extensions" / "scholar_mcp"
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != mcp_root.resolve()]
    for name in list(sys.modules):
        if name == "scholar_mcp" or name.startswith("scholar_mcp."):
            del sys.modules[name]
    return mcp_root


def test_ensure_scholar_mcp_on_path_makes_package_importable(monkeypatch) -> None:
    mcp_root = repo_root() / "extensions" / "scholar_mcp"
    assert mcp_root.is_dir()
    assert (mcp_root / "scholar_mcp" / "__init__.py").is_file()

    monkeypatch.chdir(repo_root() / "apps" / "scholarflow-api")
    monkeypatch.delenv("SCHOLAR_MCP_DIR", raising=False)
    _drop_scholar_mcp_from_path_and_modules()

    try:
        importlib.import_module("scholar_mcp")
        imported_without_ensure = True
    except ModuleNotFoundError:
        imported_without_ensure = False
    assert imported_without_ensure is False

    ensured = ensure_scholar_mcp_on_path()
    assert ensured.resolve() == mcp_root.resolve()
    assert str(mcp_root.resolve()) in sys.path
    mod = importlib.import_module("scholar_mcp.clients.github")
    assert hasattr(mod, "search_repositories")


def test_search_github_repositories_survives_api_cwd(monkeypatch) -> None:
    """In-process search is required; must not ModuleNotFoundError under API cwd."""
    monkeypatch.chdir(repo_root() / "apps" / "scholarflow-api")
    monkeypatch.delenv("SCHOLAR_MCP_DIR", raising=False)
    _drop_scholar_mcp_from_path_and_modules()

    async def _fake_search(**_kwargs):
        return [{"repository": "jianzhangcs/ISTA-Net-PyTorch"}]

    ensure_scholar_mcp_on_path()
    import scholar_mcp.clients.github as gh

    monkeypatch.setattr(gh, "search_repositories", _fake_search)
    hits = adapters.search_github_repositories("ISTA-Net", max_results=1)
    assert hits and hits[0]["repository"] == "jianzhangcs/ISTA-Net-PyTorch"
