from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .crawler import CrawlManager, CrawlParams, export_to_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Assignment 01 crawler job.")
    parser.add_argument("--pages", type=int, default=3, help="maximum listing pages (1-50)")
    parser.add_argument("--interval", type=float, default=1.0, help="delay after each request")
    parser.add_argument("--url", default="https://books.toscrape.com/", help="allowed start URL")
    parser.add_argument("--no-details", action="store_true", help="skip detail pages")
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parent.parent / "data" / "runtime"),
        help="database and raw-response directory",
    )
    parser.add_argument(
        "--export-dir",
        default="",
        help="export directory; defaults to <data-dir>/exports/<job-id>",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        params = CrawlParams(
            start_url=args.url,
            max_pages=args.pages,
            request_interval=args.interval,
            fetch_details=not args.no_details,
        )
        manager = CrawlManager(args.data_dir)
        job = manager.create(params)
        print(f"job_id={job['id']}", flush=True)
        print("status=running; waiting for completion...", flush=True)
        final = manager.wait(job["id"])
        export_dir = Path(args.export_dir) if args.export_dir else (
            Path(args.data_dir) / "exports" / job["id"]
        )
        paths = export_to_dir(manager.store, job["id"], export_dir)
        print(f"status={final['status']}", flush=True)
        print(f"pages={final['pages_done']}/{final['pages_total']}", flush=True)
        print(f"records={final['records_count']}", flush=True)
        print(f"duplicates={final['duplicates_count']}", flush=True)
        print(f"failures={final['failures_count']}", flush=True)
        print(f"message={final['message']}", flush=True)
        for kind, path in paths.items():
            print(f"{kind}={path}")
        return 0 if final["status"] == "completed" else 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
