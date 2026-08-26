#!/usr/bin/env python3

import argparse
import socket
import time


class FluidNC:
    def __init__(self, host, port=23):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        self.sock = socket.create_connection(
            (self.host, self.port),
            timeout=5,
        )
        self.sock.settimeout(5)

        # Read whatever FluidNC sends when connecting.
        try:
            data = self.sock.recv(4096)
            if data:
                print(data.decode(errors="replace"), end="")
        except socket.timeout:
            pass

    def close(self):
        if self.sock:
            self.sock.close()

    def send(self, command):
        """Send one G-code command and wait for the response."""
        self.sock.sendall((command.strip() + "\n").encode())

        while True:
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("Connection closed by FluidNC")

            text = data.decode(errors="replace")
            print(text, end="")

            if "ok" in text.lower():
                return

            if "error:" in text.lower() or "alarm:" in text.lower():
                raise RuntimeError(text.strip())

    def status(self):
        """Request the realtime machine status."""
        self.sock.sendall(b"?")

        data = self.sock.recv(4096)
        text = data.decode(errors="replace")
        print(text, end="")
        return text


def send_file(cnc, filename):
    # Count commands first so we can show progress.
    with open(filename, "r", encoding="utf-8") as f:
        lines = [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith(";")
        ]

    total = len(lines)

    print(f"Loaded {total} commands")

    for number, line in enumerate(lines, start=1):
        # Ignore comments.
        if line.startswith("("):
            continue

        cnc.send(line)

        # Don't need high-frequency status updates.
        if number % 100 == 0 or number == total:
            percent = number / total * 100
            print(f"\nProgress: {number}/{total} ({percent:.1f}%)")
            cnc.status()


def console(cnc):
    print("Interactive mode. Type 'quit' to exit.")
    print("Type '?' to query machine status.")

    while True:
        try:
            command = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not command:
            continue

        if command.lower() in {"quit", "exit"}:
            break

        if command == "?":
            cnc.status()
            continue

        try:
            cnc.send(command)
        except RuntimeError as e:
            print(f"ERROR: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="FluidNC IP address")
    parser.add_argument(
        "--file",
        help="G-code file to send",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=23,
        help="FluidNC Telnet port (default: 23)",
    )

    args = parser.parse_args()

    cnc = FluidNC(args.host, args.port)

    try:
        print(f"Connecting to {args.host}:{args.port}...")
        cnc.connect()
        print("Connected.")

        if args.file:
            send_file(cnc, args.file)
        else:
            console(cnc)

    finally:
        cnc.close()


if __name__ == "__main__":
    main()
