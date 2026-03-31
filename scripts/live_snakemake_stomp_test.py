from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse


DEFAULT_FORMATTER_CLASS = "snakemake_logger_plugin_stomp.formatters.ComprehensiveEventFormatter"


def _parse_stomp_url(url: str) -> tuple[str, int, str, str]:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 61613
    user = parsed.username or "guest"
    password = parsed.password or "guest"
    return host, port, user, password


def run_snakemake(args: argparse.Namespace) -> int:
    snakefile_path = Path(args.snakefile).resolve()
    working_directory = snakefile_path.parent
    project_root = Path(__file__).resolve().parent.parent
    plugin_src = project_root / "vendor" / "snakemake-logger-plugin-stomp" / "src"

    cmd = [
        sys.executable,
        "-m",
        "snakemake",
        "--snakefile",
        str(snakefile_path),
        "--cores",
        str(args.cores),
        "--forceall",
        "--printshellcmds",
        "--logger",
        "stomp",
        "--logger-stomp-host",
        args.stomp_host,
        "--logger-stomp-port",
        str(args.stomp_port),
        "--logger-stomp-user",
        args.stomp_user,
        "--logger-stomp-password",
        args.stomp_password,
        "--logger-stomp-queue",
        args.stomp_queue,
        "--logger-stomp-consumer-heartbeat-interval",
        "2",
        "--logger-stomp-stream-filter-by-workflow",
        "--logger-stomp-use-stream"
    ]
    cmd.extend(["--logger-stomp-formatter-class", args.formatter_class] if args.formatter_class else [])

    print(f"Snakefile:  {snakefile_path}")
    print(f"STOMP:      {args.stomp_host}:{args.stomp_port} -> {args.stomp_queue}")
    print(f"Formatter:  {args.formatter_class if args.formatter_class else 'default'}")

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    pythonpath_parts = [str(working_directory), str(project_root)]
    if plugin_src.exists():
        pythonpath_parts.append(str(plugin_src))
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = ":".join(pythonpath_parts)

    return subprocess.call(cmd, cwd=str(working_directory), env=env)


def build_arg_parser() -> argparse.ArgumentParser:
    # Honour the legacy RABBITMQ_URL env var for zero-config local use.
    default_host, default_port, default_user, default_password = _parse_stomp_url(
        os.getenv("RABBITMQ_URL", "stomp://guest:guest@rabbitmq:61613")
    )

    parser = argparse.ArgumentParser(
        description="Run a live Snakemake test using snakemake-logger-plugin-stomp."
    )
    parser.add_argument(
        "--snakefile",
        default="live_tests/snakemake/Snakefile",
        help="Path to the Snakefile to run.",
    )
    parser.add_argument("--cores", type=int, default=1, help="Snakemake cores.")
    parser.add_argument(
        "--stomp-host",
        default=default_host,
        dest="stomp_host",
        help="STOMP broker hostname.",
    )
    parser.add_argument(
        "--stomp-port",
        type=int,
        default=default_port,
        dest="stomp_port",
        help="STOMP broker port.",
    )
    parser.add_argument(
        "--stomp-user",
        default=default_user,
        dest="stomp_user",
        help="STOMP broker username.",
    )
    parser.add_argument(
        "--stomp-password",
        default=default_password,
        dest="stomp_password",
        help="STOMP broker password.",
    )
    parser.add_argument(
        "--stomp-queue",
        default="/queue/test",
        dest="stomp_queue",
        help="STOMP destination the plugin publishes to.",
    )
    parser.add_argument(
        "--formatter-class",
        dest="formatter_class",
        default=DEFAULT_FORMATTER_CLASS,
        help=(
            "Fully-qualified formatter class path for --logger-stomp-formatter-class "
            f"(default: {DEFAULT_FORMATTER_CLASS})."
        ),
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return run_snakemake(args)


if __name__ == "__main__":
    raise SystemExit(main())
