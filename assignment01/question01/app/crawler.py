from __future__ import annotations

import csv
import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

ALLOWED_HOSTS = {"books.toscrape.com"}
DEFAULT_START_URL = "https://books.toscrape.com/"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
USER_AGENT = "AssignmentCrawler/1.0 (local educational use)"

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
CAPTCHA_MARKERS = (
    "g-recaptcha",
    "h-captcha",
    "hcaptcha",
    "cf-challenge",
    "challenge-platform",
    "verify you are human",
    "verify that you are human",
    "robot check",
    "captcha",
    "验证码",
)
ACTIVE_STATUSES = ("queued", "running", "paused", "stopping")


class CrawlError(Exception):
    """Base error for crawler failures."""


class ValidationError(CrawlError):
    """Invalid user input or extracted record."""


class BusyError(CrawlError):
    """Another crawler task is active."""


class FetchError(CrawlError):
    """HTTP or transport failure."""


class AntiBotError(FetchError):
    """The target returned a rate-limit, block, or CAPTCHA response."""


class StoppedError(CrawlError):
    """The user stopped the worker."""


@dataclass(frozen=True)
class CrawlParams:
    start_url: str = DEFAULT_START_URL
    max_pages: int = 3
    request_interval: float = 1.0
    fetch_details: bool = True

    def __post_init__(self) -> None:
        normalized = validate_start_url(self.start_url)
        object.__setattr__(self, "start_url", normalized)
        if not 1 <= int(self.max_pages) <= 50:
            raise ValidationError("最大页数必须在 1 到 50 之间")
        if not 0 <= float(self.request_interval) <= 10:
            raise ValidationError("请求间隔必须在 0 到 10 秒之间")
        object.__setattr__(self, "max_pages", int(self.max_pages))
        object.__setattr__(self, "request_interval", float(self.request_interval))
        object.__setattr__(self, "fetch_details", bool(self.fetch_details))

    def as_dict(self) -> dict[str, Any]:
        return {
            "start_url": self.start_url,
            "max_pages": self.max_pages,
            "request_interval": self.request_interval,
            "fetch_details": self.fetch_details,
        }


@dataclass
class ListingItem:
    title: str
    price: str
    rating: int | None
    availability: str
    category: str
    detail_url: str


@dataclass
class ListingPage:
    items: list[ListingItem]
    next_url: str | None
    page_category: str


@dataclass
class DetailData:
    title: str
    price: str
    rating: int | None
    availability: str
    category: str
    description: str


@dataclass
class Control:
    pause_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.pause_event.set()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def validate_start_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if len(candidate) > 500:
        raise ValidationError("起始 URL 过长")
    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise ValidationError("起始 URL 格式无效") from exc
    if parts.scheme != "https":
        raise ValidationError("仅允许 HTTPS 起始 URL")
    if parts.username or parts.password:
        raise ValidationError("起始 URL 不允许包含用户名或密码")
    if parts.hostname not in ALLOWED_HOSTS:
        allowed = ", ".join(sorted(ALLOWED_HOSTS))
        raise ValidationError(f"域名不在白名单内，仅允许：{allowed}")
    if parts.port not in (None, 443):
        raise ValidationError("仅允许标准 HTTPS 端口 443")
    if not parts.path.startswith("/"):
        raise ValidationError("起始 URL 路径无效")
    return candidate


def is_allowed_url(raw_url: str) -> bool:
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname in ALLOWED_HOSTS
        and parts.port in (None, 443)
        and not parts.username
        and not parts.password
    )


def parse_price(raw_price: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", raw_price.replace(",", ""))
    return float(match.group(1)) if match else None


def parse_rating(classes: list[str] | None) -> int | None:
    for token in classes or []:
        if token in RATING_WORDS:
            return RATING_WORDS[token]
    return None


def extract_category(soup: BeautifulSoup) -> str:
    crumbs = [
        normalize_text(node.get_text(" ", strip=True))
        for node in soup.select("ul.breadcrumb li a")
    ]
    crumbs = [crumb for crumb in crumbs if crumb and crumb.lower() not in {"home", "books"}]
    return crumbs[-1] if crumbs else ""


def parse_listing(html: str, page_url: str) -> ListingPage:
    soup = BeautifulSoup(html, "lxml")
    page_category = extract_category(soup)
    items: list[ListingItem] = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        if not link:
            continue
        href = normalize_text(link.get("href"))
        detail_url = urljoin(page_url, href)
        rating_node = card.select_one("p.star-rating")
        rating_classes = rating_node.get("class", []) if rating_node else []
        items.append(
            ListingItem(
                title=normalize_text(link.get("title") or link.get_text(" ", strip=True)),
                price=normalize_text(
                    card.select_one(".price_color").get_text(" ", strip=True)
                    if card.select_one(".price_color")
                    else ""
                ),
                rating=parse_rating(rating_classes),
                availability=normalize_text(
                    card.select_one(".availability").get_text(" ", strip=True)
                    if card.select_one(".availability")
                    else ""
                ),
                category=page_category,
                detail_url=detail_url,
            )
        )
    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, normalize_text(next_link.get("href"))) if next_link else None
    if next_url and not is_allowed_url(next_url):
        next_url = None
    return ListingPage(items=items, next_url=next_url, page_category=page_category)


def parse_detail(html: str, detail_url: str) -> DetailData:
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one(".product_main h1") or soup.select_one("h1")
    price_node = soup.select_one(".product_main .price_color")
    rating_node = soup.select_one(".product_main p.star-rating")
    availability_node = soup.select_one(".product_main .availability")
    description_node = soup.select_one("#product_description")
    description = ""
    if description_node:
        paragraph = description_node.find_next_sibling("p")
        if paragraph:
            description = normalize_text(paragraph.get_text(" ", strip=True))
    return DetailData(
        title=normalize_text(title_node.get_text(" ", strip=True) if title_node else ""),
        price=normalize_text(price_node.get_text(" ", strip=True) if price_node else ""),
        rating=parse_rating(rating_node.get("class", []) if rating_node else []),
        availability=normalize_text(
            availability_node.get_text(" ", strip=True) if availability_node else ""
        ),
        category=extract_category(soup),
        description=description,
    )


def detect_antibot(html: str, status_code: int = 200) -> str | None:
    if status_code in (403, 429):
        return f"HTTP {status_code}：目标站点拒绝或限制了请求"
    lower = (html or "").lower()
    for marker in CAPTCHA_MARKERS:
        if marker in lower:
            return f"检测到验证码/人机验证特征：{marker}"
    return None


def validate_record(record: dict[str, Any], fetch_details: bool) -> tuple[bool, list[str]]:
    flags: list[str] = []
    if not record.get("title"):
        return False, ["关键字段缺失：title"]
    if not is_allowed_url(record.get("detail_url", "")):
        return False, ["关键字段无效：detail_url 不在域名白名单内"]
    if not record.get("price"):
        return False, ["关键字段缺失：price"]
    if parse_price(record["price"]) is None:
        flags.append("price_parse_failed")
    if record.get("rating") not in (1, 2, 3, 4, 5):
        flags.append("rating_missing_or_invalid")
    if not record.get("availability"):
        flags.append("availability_missing")
    if not record.get("category"):
        flags.append("category_missing")
    if fetch_details and not record.get("description"):
        flags.append("description_missing")
    return True, flags


class JobStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    start_url TEXT NOT NULL,
                    max_pages INTEGER NOT NULL,
                    request_interval REAL NOT NULL,
                    fetch_details INTEGER NOT NULL,
                    pages_total INTEGER NOT NULL DEFAULT 0,
                    pages_done INTEGER NOT NULL DEFAULT 0,
                    current_page INTEGER NOT NULL DEFAULT 0,
                    records_count INTEGER NOT NULL DEFAULT 0,
                    duplicates_count INTEGER NOT NULL DEFAULT 0,
                    failures_count INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    pause_reason TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    price TEXT NOT NULL,
                    price_gbp REAL,
                    rating INTEGER,
                    availability TEXT,
                    category TEXT,
                    detail_url TEXT NOT NULL,
                    description TEXT,
                    source_page TEXT,
                    scraped_at TEXT NOT NULL,
                    quality_flags TEXT NOT NULL DEFAULT '',
                    UNIQUE(job_id, detail_url)
                );

                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    source_url TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    http_status INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_items_job ON items(job_id, id);
                CREATE INDEX IF NOT EXISTS idx_failures_job ON failures(job_id, id);
                CREATE INDEX IF NOT EXISTS idx_logs_job ON logs(job_id, id);
                """
            )

    def recover_stale_jobs(self) -> int:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status='failed', finished_at=?, message=?
                WHERE status IN ('queued', 'running', 'paused', 'stopping')
                """,
                (now, "服务重启，未完成任务已标记为失败"),
            )
            return cursor.rowcount

    def active_job(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM jobs WHERE status IN ({','.join('?' for _ in ACTIVE_STATUSES)}) "
                "ORDER BY created_at DESC LIMIT 1",
                ACTIVE_STATUSES,
            ).fetchone()
            return dict(row) if row else None

    def create_job(self, params: CrawlParams, workspace: Path) -> str:
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, status, start_url, max_pages, request_interval, fetch_details,
                    pages_total, created_at, message
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    params.start_url,
                    params.max_pages,
                    params.request_interval,
                    int(params.fetch_details),
                    params.max_pages,
                    now,
                    "任务已创建，等待 worker 启动",
                ),
            )
        workspace.mkdir(parents=True, exist_ok=True)
        return job_id

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "status",
            "pages_done",
            "current_page",
            "records_count",
            "duplicates_count",
            "failures_count",
            "message",
            "pause_reason",
            "started_at",
            "finished_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id=?",
                (*updates.values(), job_id),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def latest_job(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def add_log(self, job_id: str, level: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO logs(job_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (job_id, level.upper(), message, utc_now()),
            )

    def get_logs(self, job_id: str, limit: int = 200, after_id: int = 0) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM logs
                WHERE job_id=? AND id>?
                ORDER BY id DESC LIMIT ?
                """,
                (job_id, max(0, after_id), max(1, min(limit, 1000))),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]

    def add_failure(
        self,
        job_id: str,
        source_url: str,
        error_type: str,
        message: str,
        http_status: int | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO failures(job_id, source_url, error_type, message, http_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, source_url, error_type, message, http_status, utc_now()),
            )
            conn.execute(
                "UPDATE jobs SET failures_count=(SELECT COUNT(*) FROM failures WHERE job_id=?) WHERE id=?",
                (job_id, job_id),
            )

    def get_failures(self, job_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM failures WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, max(1, min(limit, 1000))),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_item(self, job_id: str, record: dict[str, Any]) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO items (
                    job_id, title, price, price_gbp, rating, availability, category,
                    detail_url, description, source_page, scraped_at, quality_flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    record["title"],
                    record["price"],
                    parse_price(record["price"]),
                    record.get("rating"),
                    record.get("availability", ""),
                    record.get("category", ""),
                    record["detail_url"],
                    record.get("description", ""),
                    record.get("source_page", ""),
                    record.get("scraped_at", utc_now()),
                    ",".join(record.get("quality_flags", [])),
                ),
            )
            return cursor.rowcount > 0

    def items(self, job_id: str, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        sql = "SELECT * FROM items WHERE job_id=? ORDER BY id"
        params: list[Any] = [job_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([max(1, min(limit, 5000)), max(0, offset)])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def export_payloads(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        items = self.items(job_id)
        failures = self.get_failures(job_id, 1000)
        logs = self.get_logs(job_id, 1000)
        return {"job": job, "items": items, "failures": failures, "logs": logs}


class CrawlManager:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = JobStore(self.data_dir / "crawler.db")
        self.store.recover_stale_jobs()
        self._lock = threading.Lock()
        self._controls: dict[str, Control] = {}

    def create(self, params: CrawlParams) -> dict[str, Any]:
        with self._lock:
            active = self.store.active_job()
            if active:
                raise BusyError(
                    f"已有任务 {active['id']} 处于 {active['status']} 状态，请先等待或停止"
                )
            workspace = self.data_dir / "jobs" / "pending"
            job_id = self.store.create_job(params, workspace)
            final_workspace = self.data_dir / "jobs" / job_id
            if workspace.exists():
                workspace.rename(final_workspace)
            control = Control()
            self._controls[job_id] = control
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id, params, final_workspace, control),
                name=f"crawler-{job_id}",
                daemon=True,
            )
            thread.start()
        job = self.store.get_job(job_id)
        if not job:
            raise RuntimeError("任务创建后无法读取")
        return job

    def pause(self, job_id: str) -> dict[str, Any]:
        job = self._require_job(job_id)
        if job["status"] != "running":
            raise ValidationError("只有运行中的任务可以暂停")
        control = self._controls.get(job_id)
        if not control:
            raise ValidationError("任务 worker 不存在")
        control.pause_event.clear()
        self.store.update_job(
            job_id, status="paused", pause_reason="user", message="用户已暂停任务"
        )
        self.store.add_log(job_id, "INFO", "用户暂停任务，worker 将在安全点停止请求")
        return self._require_job(job_id)

    def resume(self, job_id: str) -> dict[str, Any]:
        job = self._require_job(job_id)
        if job["status"] != "paused":
            raise ValidationError("只有暂停中的任务可以继续")
        control = self._controls.get(job_id)
        if not control:
            raise ValidationError("任务 worker 不存在")
        prior_reason = job.get("pause_reason")
        control.pause_event.set()
        self.store.update_job(
            job_id,
            status="running",
            pause_reason=None,
            message="任务已继续",
        )
        self.store.add_log(
            job_id,
            "INFO",
            "用户继续任务" + ("（安全暂停已解除）" if prior_reason == "safety" else ""),
        )
        return self._require_job(job_id)

    def stop(self, job_id: str) -> dict[str, Any]:
        job = self._require_job(job_id)
        if job["status"] not in {"queued", "running", "paused"}:
            raise ValidationError("当前任务状态不能停止")
        control = self._controls.get(job_id)
        if not control:
            raise ValidationError("任务 worker 不存在")
        control.stop_event.set()
        control.pause_event.set()
        self.store.update_job(job_id, status="stopping", message="正在停止任务")
        self.store.add_log(job_id, "INFO", "收到停止请求，等待当前安全点")
        return self._require_job(job_id)

    def wait(self, job_id: str, timeout: float | None = None) -> dict[str, Any]:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            job = self._require_job(job_id)
            if job["status"] in {"completed", "failed", "stopped"}:
                return job
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"任务 {job_id} 在限定时间内未结束")
            time.sleep(0.2)

    def _require_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    def _run_job(
        self,
        job_id: str,
        params: CrawlParams,
        workspace: Path,
        control: Control,
    ) -> None:
        self.store.update_job(
            job_id,
            status="running",
            started_at=utc_now(),
            message="正在启动爬虫 worker",
        )
        self.store.add_log(job_id, "INFO", "worker 已启动")
        self.store.add_log(
            job_id,
            "INFO",
            f"目标 {params.start_url}；最多 {params.max_pages} 页；间隔 {params.request_interval:g} 秒；"
            f"详情页={'是' if params.fetch_details else '否'}",
        )
        raw_dir = workspace / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.8",
            }
        )
        session.trust_env = False
        records = 0
        duplicates = 0
        pages_done = 0
        try:
            page_url: str | None = params.start_url
            for page_number in range(1, params.max_pages + 1):
                if not page_url:
                    break
                if not self._wait_if_paused(job_id, control):
                    self._mark_stopped(job_id, pages_done, records)
                    return
                self.store.update_job(
                    job_id,
                    current_page=page_number,
                    message=f"正在抓取第 {page_number} 页",
                )
                self.store.add_log(job_id, "INFO", f"请求列表页 {page_number}: {page_url}")
                try:
                    html = self._fetch_html(job_id, control, page_url, raw_dir, page_number)
                    listing = parse_listing(html, page_url)
                except StoppedError:
                    self._mark_stopped(job_id, pages_done, records)
                    return
                except AntiBotError as exc:
                    self._record_failure(job_id, page_url, "anti_bot", str(exc))
                    self._mark_failed(job_id, str(exc))
                    return
                except Exception as exc:
                    self._record_failure(job_id, page_url, "listing_error", str(exc))
                    self._mark_failed(job_id, f"列表页抓取失败：{exc}")
                    return

                if not listing.items:
                    message = f"第 {page_number} 页未解析到书籍记录"
                    self._record_failure(job_id, page_url, "parse_error", message)
                    self._mark_failed(job_id, message)
                    return
                self.store.add_log(
                    job_id, "INFO", f"第 {page_number} 页解析到 {len(listing.items)} 个条目"
                )

                for item_index, summary in enumerate(listing.items, start=1):
                    if not self._wait_if_paused(job_id, control):
                        self._mark_stopped(job_id, pages_done, records)
                        return
                    record: dict[str, Any] = {
                        "title": summary.title,
                        "price": summary.price,
                        "rating": summary.rating,
                        "availability": summary.availability,
                        "category": summary.category,
                        "detail_url": summary.detail_url,
                        "description": "",
                        "source_page": page_url,
                        "scraped_at": utc_now(),
                    }
                    if params.fetch_details:
                        self.store.add_log(
                            job_id,
                            "DEBUG",
                            f"请求详情页 {page_number}.{item_index}: {summary.detail_url}",
                        )
                        try:
                            detail_html = self._fetch_html(
                                job_id,
                                control,
                                summary.detail_url,
                                raw_dir,
                                f"{page_number}-{item_index}",
                            )
                            detail = parse_detail(detail_html, summary.detail_url)
                            record.update(
                                {
                                    "title": detail.title or summary.title,
                                    "price": detail.price or summary.price,
                                    "rating": detail.rating or summary.rating,
                                    "availability": detail.availability or summary.availability,
                                    "category": detail.category or summary.category,
                                    "description": detail.description,
                                }
                            )
                        except StoppedError:
                            self._mark_stopped(job_id, pages_done, records)
                            return
                        except AntiBotError as exc:
                            self._record_failure(
                                job_id, summary.detail_url, "anti_bot", str(exc)
                            )
                            self._mark_failed(job_id, str(exc))
                            return
                        except Exception as exc:
                            self._record_failure(
                                job_id, summary.detail_url, "detail_error", str(exc)
                            )
                            self.store.add_log(
                                job_id,
                                "WARNING",
                                f"详情页失败，保留列表页字段：{summary.detail_url}；{exc}",
                            )

                    valid, flags = validate_record(record, params.fetch_details)
                    if not valid:
                        self._record_failure(job_id, summary.detail_url, "validation", "; ".join(flags))
                        self.store.add_log(
                            job_id, "WARNING", f"记录校验失败并跳过：{'; '.join(flags)}"
                        )
                        continue
                    record["quality_flags"] = flags
                    inserted = self.store.add_item(job_id, record)
                    if inserted:
                        records += 1
                        self.store.update_job(job_id, records_count=records)
                    else:
                        duplicates += 1
                        self.store.update_job(job_id, duplicates_count=duplicates)
                        self.store.add_log(job_id, "INFO", f"重复记录已跳过：{summary.detail_url}")
                    if flags:
                        self.store.add_log(
                            job_id,
                            "WARNING",
                            f"字段质量提示 {summary.detail_url}: {', '.join(flags)}",
                        )

                pages_done += 1
                self.store.update_job(job_id, pages_done=pages_done)
                self.store.add_log(
                    job_id,
                    "INFO",
                    f"第 {page_number} 页完成；累计 {records} 条，重复 {duplicates} 条",
                )
                page_url = listing.next_url
                if not page_url:
                    self.store.add_log(job_id, "INFO", "没有下一页，提前结束")
                    break

            summary = f"抓取完成：{pages_done} 页，{records} 条，重复 {duplicates} 条"
            self.store.update_job(
                job_id,
                status="completed",
                finished_at=utc_now(),
                message=summary,
                current_page=0,
            )
            self.store.add_log(job_id, "INFO", summary)
        except StoppedError:
            self._mark_stopped(job_id, pages_done, records)
        except Exception as exc:
            self._record_failure(job_id, params.start_url, "worker_error", repr(exc))
            self._mark_failed(job_id, f"worker 异常：{exc}")
        finally:
            session.close()
            with self._lock:
                self._controls.pop(job_id, None)

    def _wait_if_paused(self, job_id: str, control: Control) -> bool:
        announced = False
        while not control.stop_event.is_set():
            if control.pause_event.wait(timeout=0.2):
                if announced:
                    self.store.update_job(job_id, status="running", message="任务已继续")
                    self.store.add_log(job_id, "INFO", "worker 已恢复执行")
                return True
            if not announced:
                self.store.add_log(job_id, "INFO", "worker 已停在安全点，等待继续或停止")
                announced = True
        return False

    def _fetch_html(
        self,
        job_id: str,
        control: Control,
        url: str,
        raw_dir: Path,
        label: str | int,
    ) -> str:
        if not is_allowed_url(url):
            raise ValidationError(f"拒绝白名单外 URL：{url}")
        anti_bot_attempts = 0
        while True:
            if not self._wait_if_paused(job_id, control):
                raise StoppedError("任务已停止")
            try:
                response = self._http_get(url)
            except AntiBotError as exc:
                anti_bot_attempts += 1
                self._record_failure(job_id, url, "anti_bot", str(exc))
                self.store.add_log(job_id, "WARNING", f"安全拦截：{url}；{exc}")
                if anti_bot_attempts >= 3:
                    raise
                control.pause_event.clear()
                self.store.update_job(
                    job_id,
                    status="paused",
                    pause_reason="safety",
                    message=f"安全暂停：{exc}。检查/等待后可点击继续，连续拦截 3 次将失败",
                )
                self.store.add_log(
                    job_id,
                    "WARNING",
                    "任务因 403/429/验证码特征暂停；本程序不会破解验证码",
                )
                continue

            html = response.text
            marker = detect_antibot(html, response.status_code)
            safe_label = re.sub(r"[^0-9A-Za-z._-]+", "_", str(label))
            raw_path = raw_dir / f"response-{safe_label}.html"
            raw_path.write_text(html, encoding="utf-8")
            if marker:
                anti_bot_attempts += 1
                self._record_failure(
                    job_id, url, "anti_bot", marker, response.status_code
                )
                self.store.add_log(job_id, "WARNING", f"安全拦截：{url}；{marker}")
                if anti_bot_attempts >= 3:
                    raise AntiBotError(marker)
                control.pause_event.clear()
                self.store.update_job(
                    job_id,
                    status="paused",
                    pause_reason="safety",
                    message=f"安全暂停：{marker}。检查/等待后可点击继续，连续拦截 3 次将失败",
                )
                self.store.add_log(
                    job_id,
                    "WARNING",
                    "任务因 403/429/验证码特征暂停；本程序不会破解验证码",
                )
                continue

            self._interruptible_sleep(job_id, control)
            return html

    def _http_get(self, url: str) -> requests.Response:
        last_error: Exception | None = None
        redirect_statuses = {301, 302, 303, 307, 308}
        for attempt in range(3):
            try:
                current_url = url
                response: requests.Response | None = None
                for _redirect in range(4):
                    if not is_allowed_url(current_url):
                        raise FetchError(f"重定向到白名单外地址：{current_url}")
                    response = requests.get(
                        current_url,
                        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                        timeout=(5, 20),
                        allow_redirects=False,
                    )
                    if response.status_code not in redirect_statuses:
                        break
                    location = response.headers.get("Location", "").strip()
                    if not location:
                        raise FetchError(f"HTTP {response.status_code} 缺少重定向地址")
                    next_url = urljoin(current_url, location)
                    if not is_allowed_url(next_url):
                        raise FetchError(f"拒绝重定向到白名单外地址：{next_url}")
                    current_url = next_url
                else:
                    raise FetchError("重定向次数过多")
                if response is None:
                    raise FetchError("未收到 HTTP 响应")
                if response.status_code in (403, 429):
                    raise AntiBotError(f"HTTP {response.status_code}")
                if response.status_code >= 400:
                    raise FetchError(f"HTTP {response.status_code}")
                content_length = len(response.content)
                if content_length > MAX_RESPONSE_BYTES:
                    raise FetchError(f"响应体过大：{content_length} bytes")
                # books.toscrape.com emits UTF-8 without a charset parameter. Requests
                # otherwise guesses ISO-8859-1 and produces mojibake such as "Â£".
                response.encoding = "utf-8"
                return response
            except (requests.RequestException, FetchError) as exc:
                if isinstance(exc, AntiBotError):
                    raise
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        raise FetchError(f"请求失败：{url}；{last_error}")

    def _interruptible_sleep(self, job_id: str, control: Control) -> None:
        job = self.store.get_job(job_id)
        if not job:
            return
        seconds = float(job["request_interval"])
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not control.stop_event.is_set():
            if not control.pause_event.is_set():
                return
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

    def _record_failure(
        self,
        job_id: str,
        url: str,
        error_type: str,
        message: str,
        http_status: int | None = None,
    ) -> None:
        self.store.add_failure(job_id, url, error_type, message, http_status)

    def _mark_stopped(self, job_id: str, pages_done: int, records: int) -> None:
        self.store.update_job(
            job_id,
            status="stopped",
            finished_at=utc_now(),
            pages_done=pages_done,
            records_count=records,
            current_page=0,
            message=f"任务已停止：完成 {pages_done} 页，保存 {records} 条",
        )
        self.store.add_log(job_id, "INFO", f"任务已停止：完成 {pages_done} 页，保存 {records} 条")

    def _mark_failed(self, job_id: str, message: str) -> None:
        self.store.update_job(
            job_id,
            status="failed",
            finished_at=utc_now(),
            current_page=0,
            message=message,
        )
        self.store.add_log(job_id, "ERROR", message)


def export_to_dir(store: JobStore, job_id: str, destination: str | Path) -> dict[str, str]:
    payload = store.export_payloads(job_id)
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    job = payload["job"]
    items = payload["items"]
    failures = payload["failures"]
    logs = payload["logs"]

    fieldnames = [
        "title",
        "price",
        "price_gbp",
        "rating",
        "availability",
        "category",
        "detail_url",
        "description",
        "source_page",
        "scraped_at",
        "quality_flags",
    ]
    csv_path = output / "result.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)

    json_path = output / "result.json"
    json_path.write_text(
        json.dumps(
            {
                "job": job,
                "count": len(items),
                "items": items,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log_path = output / "run.log"
    log_path.write_text(
        "\n".join(
            f"{record['created_at']} [{record['level']}] {record['message']}" for record in logs
        )
        + ("\n" if logs else ""),
        encoding="utf-8",
    )
    failures_path = output / "failures.json"
    failures_path.write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "csv": str(csv_path),
        "json": str(json_path),
        "log": str(log_path),
        "failures": str(failures_path),
        "summary": str(summary_path),
    }


def csv_bytes(store: JobStore, job_id: str) -> bytes:
    items = store.items(job_id)
    buffer = StringIO()
    fieldnames = [
        "title",
        "price",
        "price_gbp",
        "rating",
        "availability",
        "category",
        "detail_url",
        "description",
        "source_page",
        "scraped_at",
        "quality_flags",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(items)
    return buffer.getvalue().encode("utf-8-sig")


def json_bytes(store: JobStore, job_id: str) -> bytes:
    payload = store.export_payloads(job_id)
    return json.dumps(
        {
            "job": payload["job"],
            "count": len(payload["items"]),
            "items": payload["items"],
            "failures": payload["failures"],
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


def log_bytes(store: JobStore, job_id: str) -> bytes:
    logs = store.get_logs(job_id, 1000)
    text = "\n".join(
        f"{record['created_at']} [{record['level']}] {record['message']}" for record in logs
    )
    return (text + ("\n" if text else "")).encode("utf-8")
