"""Smart setup wizard for Onshape MCP.
Configures Playwright, syncs Onshape cookies, and automatically
adds the server to Claude Desktop across macOS, Windows, and Linux.

Zero hardcoded user paths or credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .config import _BASE_DIR, settings


def get_claude_desktop_config_path() -> Path:
    """Return platform-specific path to claude_desktop_config.json."""
    system = platform.system()
    if system == "Darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    else:  # Linux / FreeBSD / other POSIX
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return base / "Claude" / "claude_desktop_config.json"


def ensure_playwright_browsers() -> bool:
    """Ensure Chromium binary is downloaded for Playwright."""
    print("[1/4] Checking Playwright browser dependencies...")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            print("  ✓ Chromium browser engine is installed and ready.")
            return True
        else:
            print(f"  ⚠ Note: Playwright browser check returned: {res.stderr.strip()[:100]}")
            return True
    except Exception as e:
        print(f"  ⚠ Could not run playwright install: {e}")
        return False


def sync_onshape_cookies(interactive: bool = True) -> bool:
    """Check for Onshape cookies or sync from local browsers or interactive login."""
    print("[2/4] Checking Onshape authentication & session cookies...")

    # 1. Existing cookie file
    if settings.onshape_cookie_file.exists() and settings.onshape_cookie_file.stat().st_size > 20:
        try:
            data = json.loads(settings.onshape_cookie_file.read_text(encoding="utf-8"))
            if data and isinstance(data, list):
                print(f"  ✓ Existing session found ({len(data)} cookies) at: {settings.onshape_cookie_file}")
                return True
        except Exception:
            pass

    # 2. Extract from installed browsers
    try:
        import browser_cookie3

        browser_loaders = [
            ("Google Chrome", getattr(browser_cookie3, "chrome", None)),
            ("Brave", getattr(browser_cookie3, "brave", None)),
            ("Microsoft Edge", getattr(browser_cookie3, "edge", None)),
            ("Chromium", getattr(browser_cookie3, "chromium", None)),
            ("Firefox", getattr(browser_cookie3, "firefox", None)),
            ("Arc", getattr(browser_cookie3, "arc", None)),
            ("Opera", getattr(browser_cookie3, "opera", None)),
            ("Vivaldi", getattr(browser_cookie3, "vivaldi", None)),
        ]
        for browser_name, loader in browser_loaders:
            if loader is None:
                continue
            try:
                cj = loader(domain_name="onshape.com")
                raw = []
                for c in cj:
                    cookie = {
                        "name": c.name,
                        "value": c.value,
                        "domain": c.domain,
                        "path": c.path,
                        "secure": bool(c.secure),
                        "httpOnly": bool(
                            c.has_nonstandard_attr("HttpOnly")
                            or c.has_nonstandard_attr("httponly")
                        ),
                    }
                    if c.expires:
                        cookie["expires"] = float(c.expires)
                    raw.append(cookie)
                if raw:
                    settings.onshape_cookie_file.parent.mkdir(parents=True, exist_ok=True)
                    settings.onshape_cookie_file.write_text(
                        json.dumps(raw, indent=2), encoding="utf-8"
                    )
                    print(
                        f"  ✓ Auto-synced {len(raw)} Onshape cookies from {browser_name}."
                    )
                    return True
            except Exception:
                continue
    except Exception:
        pass

    # 3. If missing and interactive, offer browser login
    if interactive:
        print("  ⚠ No active Onshape session found in local browsers.")
        choice = input("  [?] Would you like to open a browser window to log in now? [Y/n]: ").strip().lower()
        if choice not in ("n", "no"):
            import asyncio
            from .driver import login_interactive

            asyncio.run(login_interactive())
            return settings.onshape_cookie_file.exists()

    print("  ⚠ Please log into https://cad.onshape.com in your browser before running commands.")
    return False


def configure_claude_desktop(
    doc_url: str = "",
    use_local_env: bool = False,
    auto_yes: bool = False,
) -> Path | None:
    path = get_claude_desktop_config_path()
    _write_mcp_json(path, doc_url)
    return path


def _write_mcp_json(config_path: Path, doc_url: str = "") -> bool:
    """Helper to safely read, backup, and inject the onshape MCP entry into any mcp.json file."""
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            bak_path = config_path.with_suffix(".json.bak")
            shutil.copy2(config_path, bak_path)
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    if not isinstance(data, dict):
        data = {}

    if "mcpServers" not in data:
        data["mcpServers"] = {}

    server_entry: dict[str, Any] = {
        "command": "uvx",
        "args": [
            "--from",
            "git+https://github.com/WilliamSamson/onshape-mcp",
            "onshape-mcp",
        ],
    }
    if doc_url:
        server_entry["env"] = {"ONSHAPE_DEFAULT_DOC": doc_url}

    data["mcpServers"]["onshape"] = server_entry

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def detect_supported_clients() -> list[tuple[str, Path]]:
    """Detect all installed AI clients (Claude Desktop, Cursor, Windsurf, VS Code Cline)."""
    clients: list[tuple[str, Path]] = []

    # 1. Claude Desktop
    claude_cfg = get_claude_desktop_config_path()
    if claude_cfg.parent.exists() or claude_cfg.exists():
        clients.append(("Claude Desktop", claude_cfg))

    # 2. Cursor IDE
    cursor_dir = Path.home() / ".cursor"
    cursor_cfg = cursor_dir / "mcp.json"
    if cursor_dir.exists() or cursor_cfg.exists():
        clients.append(("Cursor IDE", cursor_cfg))

    # 3. Windsurf
    windsurf_dir = Path.home() / ".codeium" / "windsurf"
    windsurf_cfg = windsurf_dir / "mcp_config.json"
    if windsurf_dir.exists() or windsurf_cfg.exists():
        clients.append(("Windsurf IDE", windsurf_cfg))

    # 4. VS Code (Cline extension)
    system = platform.system()
    if system == "Darwin":
        vscode_base = Path.home() / "Library" / "Application Support" / "Code"
    elif system == "Windows":
        app_data = os.environ.get("APPDATA")
        vscode_base = (Path(app_data) if app_data else Path.home() / "AppData" / "Roaming") / "Code"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        vscode_base = (Path(xdg_config) if xdg_config else Path.home() / ".config") / "Code"

    cline_cfg = vscode_base / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    if cline_cfg.parent.exists() or cline_cfg.exists():
        clients.append(("VS Code (Cline)", cline_cfg))

    roo_cfg = vscode_base / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json"
    if roo_cfg.parent.exists() or roo_cfg.exists():
        clients.append(("VS Code (Roo Code)", roo_cfg))

    return clients


def configure_detected_clients(
    doc_url: str = "",
    auto_yes: bool = False,
) -> list[str]:
    """Auto-configure all detected AI clients."""
    print("[4/4] Configuring AI Client Integrations (Claude, Cursor, VS Code, etc.)...")
    detected = detect_supported_clients()
    configured: list[str] = []

    if not detected:
        print("  ℹ No desktop AI clients (Claude, Cursor, Windsurf, Cline) detected automatically.")
        # Offer default Claude Desktop location
        default_claude = get_claude_desktop_config_path()
        choice = "y" if auto_yes else input(
            f"  [?] Create Claude Desktop config anyway at:\n      {default_claude}? [Y/n]: "
        ).strip().lower()
        if choice not in ("n", "no"):
            _write_mcp_json(default_claude, doc_url)
            configured.append(f"Claude Desktop ({default_claude})")
            print(f"  ✓ Configured Claude Desktop at: {default_claude}")
        return configured

    for name, path in detected:
        if not auto_yes:
            choice = input(f"  [?] Auto-configure {name} at:\n      {path}? [Y/n]: ").strip().lower()
            if choice in ("n", "no"):
                print(f"  Skipped {name}.")
                continue
        _write_mcp_json(path, doc_url)
        configured.append(f"{name} ({path})")
        print(f"  ✓ Configured {name} at: {path}")

    return configured


def run_setup(
    doc_url: str = "",
    auto_yes: bool = False,
    skip_browser_install: bool = False,
) -> None:
    print("=" * 68)
    print("        Onshape MCP — 1-Click Multi-AI Setup & Tester Wizard")
    print("=" * 68)
    print(f"Base data directory: {_BASE_DIR}\n")

    # 1. Playwright install
    if not skip_browser_install:
        ensure_playwright_browsers()
    else:
        print("[1/4] Skipping browser download flag.")

    print()

    # 2. Cookie sync
    sync_onshape_cookies(interactive=not auto_yes)
    print()

    # 3. Document URL
    print("[3/4] Document Configuration...")
    final_doc_url = doc_url
    if not final_doc_url and not auto_yes:
        try:
            val = input(
                "  [?] Default Onshape Document URL (optional, press Enter to skip):\n      > "
            ).strip()
            if val:
                final_doc_url = val
        except (EOFError, KeyboardInterrupt):
            pass

    if final_doc_url:
        env_file = _BASE_DIR / ".env"
        existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
        if "ONSHAPE_DEFAULT_DOC=" in existing:
            import re
            new_text = re.sub(r"ONSHAPE_DEFAULT_DOC=.*", f"ONSHAPE_DEFAULT_DOC={final_doc_url}", existing)
        else:
            new_text = existing + f"\nONSHAPE_DEFAULT_DOC={final_doc_url}\n"
        env_file.write_text(new_text, encoding="utf-8")
        print(f"  ✓ Saved default document URL to {env_file}")
    else:
        print("  ✓ No default document set (you can specify URLs per prompt).")

    print()

    # 4. Client config
    configured = configure_detected_clients(
        doc_url=final_doc_url,
        auto_yes=auto_yes,
    )
    print()

    # Summary
    print("=" * 68)
    print("🎉 Setup Complete!")
    print("=" * 68)
    if configured:
        print("Configured Desktop Clients:")
        for c in configured:
            print(f"  • {c}")
        print("\nRestart your AI client, then ask:")
        print("  'Draw a 10cm by 5cm box on the Top plane in Onshape'")
    else:
        print("Manual Desktop Config (Claude Desktop, Cursor, Windsurf):")
        print(
            json.dumps(
                {
                    "mcpServers": {
                        "onshape": {
                            "command": "uvx",
                            "args": [
                                "--from",
                                "git+https://github.com/WilliamSamson/onshape-mcp",
                                "onshape-mcp",
                            ],
                        }
                    }
                },
                indent=2,
            )
        )

    print("-" * 68)
    print("🌐 Using Web Versions Only? (ChatGPT Web, LibreChat, Open WebUI):")
    print("1. Start the server in SSE mode:")
    print("   onshape-mcp --transport sse --port 8000")
    print("2. Expose it via a secure tunnel (e.g. Cloudflare or Localtunnel):")
    print("   cloudflared tunnel --url http://localhost:8000")
    print("   # Or: npx localtunnel --port 8000")
    print("3. Paste the resulting URL (e.g. https://xxxx.trycloudflare.com/sse)")
    print("   into your web AI connector / LibreChat / Open WebUI!")
    print("=" * 68)


def main() -> None:
    parser = argparse.ArgumentParser(description="Onshape MCP 1-Click Setup Wizard")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all prompts")
    parser.add_argument("--doc-url", default="", help="Default Onshape document URL to operate on")
    parser.add_argument("--skip-browsers", action="store_true", help="Skip downloading Chromium")
    args = parser.parse_args()

    run_setup(
        doc_url=args.doc_url,
        auto_yes=args.yes,
        skip_browser_install=args.skip_browsers,
    )


if __name__ == "__main__":
    main()
