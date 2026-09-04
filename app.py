from __future__ import annotations

import argparse

from gateway.server import run_gateway_server


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Guard Gateway HTTP 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    run_gateway_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
