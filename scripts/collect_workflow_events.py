from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import signal
import sys
import threading
import time
from urllib.parse import urlparse

import stomp
from stomp.exception import ConnectFailedException, StompException


def _parse_stomp_url(url: str) -> tuple[str, int, str, str, str]:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 61613
    user = parsed.username or "guest"
    password = parsed.password or "guest"
    virtual_host = parsed.path if parsed.path else "/"
    return host, port, user, password, virtual_host


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maybe_parse_json(raw_message: str) -> object | None:
    try:
        return json.loads(raw_message)
    except json.JSONDecodeError:
        return None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _stream_subscribe_destination(destination: str, use_stream: bool) -> str:
    if not use_stream:
        return destination
    if destination.startswith("/queue/"):
        return "/amq/queue/" + destination.removeprefix("/queue/")
    return destination


class StreamOffsetProbeListener(stomp.ConnectionListener):
    def __init__(self) -> None:
        self.last_stream_offset: int | None = None
        self.done = threading.Event()

    def on_message(self, frame: stomp.utils.Frame) -> None:
        raw_offset = frame.headers.get("x-stream-offset")
        if raw_offset is not None:
            try:
                self.last_stream_offset = int(raw_offset)
            except ValueError:
                self.last_stream_offset = None

        self.done.set()


def _resolve_last_x_stream_offset(
    connection: stomp.Connection12,
    destination: str,
    ack_mode: str,
    max_events: int,
    timeout_seconds: float,
) -> str:
    """Resolve offset for the last X events using a two-step probe.

    1) Subscribe with x-stream-offset=last to capture the most recent event.
    2) Read x-stream-offset=N from that event, then return offset=max(N-X+1, 0).
    """
    probe_id = "workflow-events-offset-probe"
    probe_listener = StreamOffsetProbeListener()
    connection.set_listener(probe_id, probe_listener)

    try:
        connection.subscribe(
            destination=destination,
            id=probe_id,
            ack=ack_mode,
            headers={
                "x-stream-offset": "last",
                "prefetch-count": "1",
            },
        )
        probe_listener.done.wait(timeout=max(timeout_seconds, 0.1))
    finally:
        try:
            connection.unsubscribe(id=probe_id)
        except Exception:
            pass

    if probe_listener.last_stream_offset is None:
        return "last"

    start_offset = max(probe_listener.last_stream_offset - max_events + 1, 0)
    return f"offset={start_offset}"


class FileWriterListener(stomp.ConnectionListener):
    def __init__(
        self,
        output_path: Path,
        quiet: bool,
        connection: stomp.Connection12 | None = None,
        subscription_id: str | None = None,
        ack_enabled: bool = False,
    ) -> None:
        self.output_path = output_path
        self.quiet = quiet
        self.connection = connection
        self.subscription_id = subscription_id
        self.ack_enabled = ack_enabled
        self.capture_enabled = False
        self._lock = threading.Lock()
        self._message_count = 0
        self._last_message_monotonic: float | None = None
        self._last_error_headers: dict[str, str] | None = None
        self._last_error_body: str | None = None

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def last_error_body(self) -> str | None:
        return self._last_error_body

    @property
    def last_error_headers(self) -> dict[str, str] | None:
        return self._last_error_headers

    @property
    def last_message_monotonic(self) -> float | None:
        with self._lock:
            return self._last_message_monotonic

    def _write_record(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with self.output_path.open("a", encoding="utf-8") as output_file:
                output_file.write(line)
                output_file.write("\n")

    def on_error(self, frame: stomp.utils.Frame) -> None:
        payload = {
            "received_at": _utc_now_iso(),
            "kind": "broker_error",
            "headers": dict(frame.headers),
            "body": frame.body,
        }
        self._write_record(payload)
        with self._lock:
            self._last_error_headers = dict(frame.headers)
            self._last_error_body = frame.body
        if not self.quiet:
            print("Broker error frame received and written to log.", file=sys.stderr)

    def on_message(self, frame: stomp.utils.Frame) -> None:
        if not self.capture_enabled:
            return

        parsed_body = _maybe_parse_json(frame.body)
        payload = {
            "received_at": _utc_now_iso(),
            "kind": "message",
            "headers": dict(frame.headers),
            "body": frame.body,
        }
        if parsed_body is not None:
            payload["body_json"] = parsed_body

        self._write_record(payload)

        with self._lock:
            self._message_count += 1
            self._last_message_monotonic = time.monotonic()
            current_count = self._message_count

        if not self.quiet:
            event_name = None
            if isinstance(parsed_body, dict):
                raw_event = parsed_body.get("event")
                if raw_event is None:
                    event_name = "CONSUMER_HEARTBEAT"
                elif isinstance(raw_event, dict):
                    event_name = raw_event.get("event") or raw_event.get("type")
                elif isinstance(raw_event, str):
                    event_name = raw_event
            summary = f"event={event_name}" if event_name else "event=unknown"
            print(f"[{current_count}] Captured message ({summary}).")

        if self.ack_enabled and self.connection and self.connection.is_connected():
            ack_id = frame.headers.get("ack") or frame.headers.get("message-id")
            if ack_id:
                self.connection.ack(id=ack_id)


def build_parser() -> argparse.ArgumentParser:
    default_host, default_port, default_user, default_password, default_virtual_host = _parse_stomp_url(
        os.getenv("RABBITMQ_URL", "stomp://guest:guest@localhost:61613")
    )
    default_user = os.getenv("STOMP_USER") or os.getenv("RABBITMQ_USER") or default_user
    default_password = os.getenv("STOMP_PASSWORD") or os.getenv("RABBITMQ_PASSWORD") or default_password

    parser = argparse.ArgumentParser(
        description="Consume workflow events over STOMP and append all raw messages to a JSONL file."
    )
    parser.add_argument("--host", default=default_host, help="STOMP broker host.")
    parser.add_argument("--port", type=int, default=default_port, help="STOMP broker port.")
    parser.add_argument("--user", default=default_user, help="STOMP username.")
    parser.add_argument("--password", default=default_password, help="STOMP password.")
    parser.add_argument(
        "--virtual-host",
        default=os.getenv("STOMP_VHOST", default_virtual_host),
        dest="virtual_host",
        help="STOMP virtual host used in CONNECT host header.",
    )
    parser.add_argument(
        "--destination",
        default=os.getenv("STOMP_DESTINATION") or os.getenv("STOMP_STREAM_QUEUE") or "/queue/snakemake.events",
        help="STOMP destination to subscribe to.",
    )
    parser.add_argument(
        "--output",
        default="workflow-events.jsonl",
        help="Path to JSONL file where received events are appended.",
    )
    parser.add_argument(
        "--subscription-id",
        default="workflow-events-collector",
        help="Subscription id for the STOMP SUBSCRIBE frame.",
    )
    parser.add_argument(
        "--heartbeat-send-ms",
        type=int,
        default=10000,
        help="Client heartbeat send interval in milliseconds.",
    )
    parser.add_argument(
        "--heartbeat-recv-ms",
        type=int,
        default=10000,
        help="Client heartbeat receive interval in milliseconds.",
    )
    parser.add_argument(
        "--use-stream",
        action="store_true",
        default=_env_flag("STOMP_USE_STREAM", default=True),
        help=(
            "Treat destination as RabbitMQ stream. Converts /queue/<name> to "
            "/amq/queue/<name> for SUBSCRIBE and sends stream headers."
        ),
    )
    parser.add_argument(
        "--stream-offset",
        default=os.getenv("STOMP_STREAM_OFFSET", "last"),
        help=(
            "RabbitMQ stream offset for SUBSCRIBE (e.g. next, last, first, "
            "offset=0, timestamp=<ms>)."
        ),
    )
    parser.add_argument(
        "--stream-filter",
        default=os.getenv("STOMP_STREAM_FILTER"),
        help="Optional RabbitMQ x-stream-filter value to match filtered stream messages.",
    )
    parser.add_argument(
        "--prefetch-count",
        type=int,
        default=int(os.getenv("STOMP_PREFETCH_COUNT", "100")),
        help=(
            "STOMP prefetch-count credit for stream consumers. RabbitMQ streams "
            "require this to be set."
        ),
    )
    parser.add_argument(
        "--ack-mode",
        choices=("auto", "client", "client-individual"),
        default=os.getenv("STOMP_ACK_MODE"),
        help="STOMP SUBSCRIBE ack mode. Defaults to client-individual for streams, auto otherwise.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=int(os.getenv("STOMP_MAX_EVENTS", "100")),
        help="Maximum number of events to capture before exiting (batch mode).",
    )
    parser.add_argument(
        "--idle-timeout-seconds",
        type=float,
        default=float(os.getenv("STOMP_IDLE_TIMEOUT_SECONDS", "2")),
        help=(
            "In batch mode, stop after this many idle seconds with no new messages. "
            "Use 0 to disable idle timeout."
        ),
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        default=_env_flag("STOMP_FOLLOW", default=False),
        help="Keep listening for live events until interrupted.",
    )
    parser.add_argument(
        "--offset-probe-timeout-seconds",
        type=float,
        default=float(os.getenv("STOMP_OFFSET_PROBE_TIMEOUT_SECONDS", "2")),
        help="Timeout (seconds) for the initial stream-offset probe when collecting last X events.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-message console output.",
    )
    parser.add_argument(
        "--debug-stomp",
        action="store_true",
        help="Enable verbose stomp.py transport/protocol logging.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.debug_stomp:
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )
        else:
            logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("stomp.py").setLevel(logging.DEBUG)
        logging.getLogger("stomp").setLevel(logging.DEBUG)
        print("STOMP debug logging enabled.", file=sys.stderr)

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ack_mode = args.ack_mode or ("client-individual" if args.use_stream else "auto")

    connection = stomp.Connection12(
        host_and_ports=[(args.host, args.port)],
        heartbeats=(args.heartbeat_send_ms, args.heartbeat_recv_ms),
        keepalive=True,
        vhost=args.virtual_host,
    )
    listener = FileWriterListener(
        output_path=output_path,
        quiet=args.quiet,
        connection=connection,
        subscription_id=args.subscription_id,
        ack_enabled=ack_mode != "auto",
    )
    connection.set_listener("collector", listener)

    should_stop = threading.Event()

    def stop_handler(signum: int, _frame: object) -> None:
        if not args.quiet:
            print(f"Signal {signum} received. Stopping consumer...")
        should_stop.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    print(f"Connecting to STOMP broker at {args.host}:{args.port} (vhost={args.virtual_host})...")
    try:
        connection.connect(
            login=args.user,
            passcode=args.password,
            wait=True,
        )
    except ConnectFailedException as exc:
        print(f"STOMP connect failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        broker_headers = listener.last_error_headers
        broker_error = listener.last_error_body
        if broker_headers:
            print(f"Broker ERROR headers: {json.dumps(broker_headers, ensure_ascii=False)}", file=sys.stderr)
        if broker_error:
            print(f"Connection failed: {broker_error}", file=sys.stderr)
        else:
            print("Connection failed before broker accepted CONNECT.", file=sys.stderr)
        if args.user == "guest" and args.host not in {"localhost", "127.0.0.1"}:
            print(
                "RabbitMQ often blocks remote logins for guest user; use a non-guest account.",
                file=sys.stderr,
            )
        print(
            "Try passing --virtual-host / and valid broker credentials with --user/--password.",
            file=sys.stderr,
        )
        return 1
    except (StompException, OSError) as exc:
        print(f"STOMP transport error during connect: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    subscribe_destination = _stream_subscribe_destination(args.destination, args.use_stream)
    effective_stream_offset = args.stream_offset

    if args.use_stream and not args.follow and args.stream_offset == "last" and args.max_events > 1:
        effective_stream_offset = _resolve_last_x_stream_offset(
            connection=connection,
            destination=subscribe_destination,
            ack_mode=ack_mode,
            max_events=args.max_events,
            timeout_seconds=args.offset_probe_timeout_seconds,
        )

    subscribe_headers: dict[str, str] = {}
    if args.use_stream:
        subscribe_headers["x-stream-offset"] = str(effective_stream_offset)
        subscribe_headers["prefetch-count"] = str(args.prefetch_count)
        if args.stream_filter:
            subscribe_headers["x-stream-filter"] = args.stream_filter

    connection.subscribe(
        destination=subscribe_destination,
        id=args.subscription_id,
        ack=ack_mode,
        headers=subscribe_headers,
    )
    listener.capture_enabled = True

    print(f"Subscribed to {subscribe_destination}")
    if args.use_stream:
        print(f"Stream offset: {effective_stream_offset} (requested: {args.stream_offset})")
        print(f"Prefetch count: {args.prefetch_count}")
        if args.stream_filter:
            print(f"Stream filter: {args.stream_filter}")
    print(f"Ack mode: {ack_mode}")
    print(f"Writing events to {output_path}")
    if args.follow:
        print("Follow mode enabled. Press Ctrl+C to stop.")
    else:
        print(
            "Batch mode enabled: collecting recent events and exiting "
            f"(max_events={args.max_events}, idle_timeout_seconds={args.idle_timeout_seconds})."
        )

    started_monotonic = time.monotonic()
    try:
        while not should_stop.is_set():
            time.sleep(0.2)
            if args.follow:
                continue

            if args.max_events > 0 and listener.message_count >= args.max_events:
                if not args.quiet:
                    print(f"Reached max events ({args.max_events}). Stopping consumer...")
                should_stop.set()
                continue

            if args.idle_timeout_seconds > 0:
                last_message_monotonic = listener.last_message_monotonic
                last_activity = (
                    last_message_monotonic
                    if last_message_monotonic is not None
                    else started_monotonic
                )
                if (time.monotonic() - last_activity) >= args.idle_timeout_seconds:
                    if not args.quiet:
                        print("Idle timeout reached. Stopping consumer...")
                    should_stop.set()
    finally:
        if connection.is_connected():
            connection.disconnect()

    print(f"Stopped. Total messages captured: {listener.message_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())