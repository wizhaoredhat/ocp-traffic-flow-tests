#!/usr/bin/env python3

import argparse
import os
import random
import socket
import sys
import time

from contextlib import contextmanager
from typing import Iterator
from typing import Optional
from typing import Callable


DEFAULT_ADDR = "127.0.0.1"
DEFAULT_BUFSIZE = 65495
DEFAULT_DURATION = 0.0
DEFAULT_NUM_CLIENTS = 1
DEFAULT_PORT = 5201
DEFAULT_SLEEP = 0.001

global_start_time = time.monotonic()


def create_socket() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


@contextmanager
def socket_timeout(
    log_name: str,
    s: socket.socket,
    start_time: float,
    duration: float,
    *,
    done_msg: Optional[Callable[[], None]] = None,
) -> Iterator[socket.socket]:
    if duration <= 0.0:
        t = None
    else:
        t = (start_time + duration) - time.monotonic()
        if t <= 0.0:
            print(f"{log_name}: duration expired. Quit")
            sys.exit(0)
    s.settimeout(t)

    try:
        yield s
    except socket.timeout:
        if done_msg is not None:
            done_msg()
        print(f"{log_name}: duration expired. Quit")
        sys.exit(0)


def sleep_timeout(
    log_name: str,
    start_time: float,
    duration: float,
    sleep_time: float,
    *,
    exit_code: Optional[int] = None,
    done_msg: Optional[Callable[[], None]] = None,
) -> bool:
    if sleep_time <= 0.0:
        if duration <= 0.0:
            return True
        t = (start_time + duration) - time.monotonic()
    else:
        if duration <= 0.0:
            time.sleep(sleep_time)
            return True
        t = (start_time + duration) - time.monotonic()
        if t > 0.0:
            time.sleep(min(t, sleep_time))
            t = (start_time + duration) - time.monotonic()

    if t > 0.0:
        return True

    if done_msg is not None:
        done_msg()
    if exit_code is None:
        exit_code = 0
    print(f"{log_name}: duration expired. Quit")
    sys.exit(exit_code)


def run_server(
    *,
    s_addr: str = DEFAULT_ADDR,
    port: int = DEFAULT_PORT,
    sleep: float = DEFAULT_SLEEP,
    bufsize: int = DEFAULT_BUFSIZE,
    duration: float = DEFAULT_DURATION,
    num_clients: int = DEFAULT_NUM_CLIENTS,
) -> None:

    start_time = global_start_time

    s = create_socket()

    print(f"server: listen on {s_addr}:{port}")
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((s_addr, port))
    s.listen(1)

    client_count = 0

    while 1:
        if num_clients > 0 and client_count >= num_clients:
            print(f"server: number of clients {num_clients} reached. Quit")
            sys.exit(0)
        with socket_timeout("server", s, start_time, duration):
            conn, addr = s.accept()
        client_count += 1
        print(
            f"server: new connection #{client_count} on port {port} from addr {addr}."
        )
        msg_count = 0
        last_time = -1000.0
        rcv_len = 0
        while 1:

            def done_msg() -> None:
                print(
                    f"server: {msg_count} chunks received and returned ({rcv_len} bytes) in total"
                )

            with socket_timeout(
                "server", conn, start_time, duration, done_msg=done_msg
            ):
                try:
                    data = conn.recv(bufsize)
                except Exception:
                    data = b""
            if not data:
                done_msg()
                print(f"server: connection {addr} closed")
                break
            msg_count += 1
            rcv_len += len(data)
            with socket_timeout(
                "server", conn, start_time, duration, done_msg=done_msg
            ):
                try:
                    conn.sendall(data)
                except ConnectionResetError:
                    done_msg()
                    print(f"server: connection {addr} closed")
                    break
            now_time = time.monotonic()
            if now_time - last_time >= 1.0:
                print(
                    f"server: {msg_count} chunks received and returned ({rcv_len} bytes)"
                )
                last_time = now_time
            sleep_timeout("server", start_time, duration, sleep, done_msg=done_msg)
        conn.close()


def run_client(
    *,
    s_addr: str = DEFAULT_ADDR,
    port: int = DEFAULT_PORT,
    sleep: float = DEFAULT_SLEEP,
    bufsize: int = DEFAULT_BUFSIZE,
    duration: float = DEFAULT_DURATION,
) -> None:

    start_time = global_start_time

    print(f"client: connecting to {s_addr}:{port}")
    s = create_socket()

    first_attempt = True
    connected = False
    while not connected:
        try:
            with socket_timeout("client", s, start_time, duration):
                s.connect((s_addr, port))
        except (ConnectionRefusedError, ConnectionAbortedError):
            if first_attempt:
                first_attempt = False
                print("client: connection refused. Retry")
            sleep_timeout("client", start_time, min(duration, 60.0), 0.5, exit_code=1)
        else:
            connected = True
    print(f"client: connected to {s_addr}:{port}")

    msg_count = 0
    rcv_len = 0
    while 1:

        def done_msg() -> None:
            print(
                f"client: {msg_count} chunks send and received ({rcv_len} bytes) in total"
            )

        i_bufsize = random.randint(1, bufsize)
        snd_data = os.urandom(i_bufsize)
        with socket_timeout("client", s, start_time, duration, done_msg=done_msg):
            s.sendall(snd_data)
        msg_count += 1

        # We first read all the data we sent back.
        rcv_data = b""
        while len(rcv_data) < len(snd_data):
            s.settimeout(0.5)
            try:
                r = s.recv(bufsize)
            except socket.timeout:
                print("client: unexpected response. Server did not echo expected data")
                sys.exit(1)
            assert r
            rcv_data += r

        if rcv_data != snd_data:
            print("client: unexpected response. Expect an echo of the data we sent")
            sys.exit(1)

        rcv_len += len(rcv_data)

        if msg_count % 10000 == 0:
            print(
                f"client: {msg_count} chunks send and received ({rcv_len} bytes) for {s.getsockname()}->{s_addr}:{port}"
            )
        sleep_timeout("client", start_time, duration, sleep, done_msg=done_msg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple TCP echo server/client")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="TCP port to listen/connect (default: {DEFAULT_PORT})",
        default=DEFAULT_PORT,
    )
    parser.add_argument(
        "-a",
        "--addr",
        type=str,
        help=f"IP address to listen/connect (default: {DEFAULT_ADDR}",
        default=DEFAULT_ADDR,
    )
    parser.add_argument(
        "-s",
        "--server",
        action="store_true",
        help="Whether to run as server or client (default)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        help="How many second to sleep between client send or server receive (default: {DEFAULT_SLEEP})",
        default=DEFAULT_SLEEP,
    )
    parser.add_argument(
        "--bufsize",
        type=int,
        help="The maximum size of the chunk send at once on the TCP stream (default: {DEFAULT_BUFSIZE})",
        default=DEFAULT_BUFSIZE,
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        help=f"How long before quitting (0 means infinity) (default: {DEFAULT_DURATION})",
        default=DEFAULT_DURATION,  # noqa: E225
    )
    parser.add_argument(
        "--num-clients",
        type=int,
        help=f"For the server, how many clients are accepted (server can only handle one client at a time) (default: {DEFAULT_NUM_CLIENTS})",
        default=DEFAULT_NUM_CLIENTS,  # noqa: E225
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.server:
        run_server(
            s_addr=args.addr,
            port=args.port,
            sleep=args.sleep,
            bufsize=args.bufsize,
            duration=args.duration,
            num_clients=args.num_clients,
        )
    else:
        run_client(
            s_addr=args.addr,
            port=args.port,
            sleep=args.sleep,
            bufsize=args.bufsize,
            duration=args.duration,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
