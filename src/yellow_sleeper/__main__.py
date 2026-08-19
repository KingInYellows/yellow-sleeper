from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yellow-sleeper")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["serve-http", "serve-mcp-http"],
        help="omit to run the stdio MCP server",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    if args.command is None:
        if any(flag in (argv or sys.argv[1:]) for flag in ("-h", "--help")):
            return 0
        from .server import mcp

        mcp.run()
        return 0

    if args.command == "serve-http":
        from .web import serve_http

        serve_http(host=args.host, port=args.port or 8091)
        return 0

    from .web import serve_mcp_http

    serve_mcp_http(host=args.host, port=args.port or 8092)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
