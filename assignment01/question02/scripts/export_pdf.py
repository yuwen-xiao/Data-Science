#!/usr/bin/env python3
"""Export the generated Reveal.js deck to a 4:3 PDF and trim blank tail pages."""

from __future__ import annotations

import http.server
import socket
import subprocess
import threading
import time
from functools import partial
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUTPUT = DIST / "assignment01-question02-pca.pdf"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    if not (DIST / "index.html").exists():
        raise SystemExit("dist/index.html 不存在，请先运行 jyyslide-md 转换。")
    if not CHROME.exists():
        raise SystemExit(f"找不到 Chrome：{CHROME}")

    port = free_port()
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)

    try:
        subprocess.run(
            [
                str(CHROME),
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--virtual-time-budget=8000",
                f"--print-to-pdf={OUTPUT}",
                f"http://127.0.0.1:{port}/?print-pdf",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        server.shutdown()
        server.server_close()

    reader = PdfReader(str(OUTPUT))
    writer = PdfWriter()
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        if text or xobjects:
            writer.add_page(page)

    temporary = OUTPUT.with_suffix(".trimmed.pdf")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(OUTPUT)
    print(f"PDF: {OUTPUT}")
    print(f"Pages: {len(PdfReader(str(OUTPUT)).pages)}")


if __name__ == "__main__":
    main()
