from __future__ import annotations

import sys


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("yellow-sleeper: local stdio MCP server")
        print("usage: yellow-sleeper")
        print()
        print("Configure sleeper_league_id and sleeper_username in")
        print(".yellow-sleeper.yaml (see .yellow-sleeper.yaml.example) or via")
        print("SLEEPER_LEAGUE_ID and SLEEPER_USERNAME before league tools.")
        print("Help and dynasty_health_check work without identity.")
        return 0

    from .server import mcp

    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
