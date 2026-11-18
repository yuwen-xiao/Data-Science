from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.crawler import (
    CrawlError,
    CrawlParams,
    JobStore,
    detect_antibot,
    parse_detail,
    parse_listing,
    validate_start_url,
)


LISTING_HTML = """
<html><body>
<ul class="breadcrumb">
  <li><a href="/">Home</a></li>
  <li><a href="/catalogue/category/books/mystery_3/">Mystery</a></li>
</ul>
<article class="product_pod">
  <h3><a href="../../../book-one_1/index.html" title="Book One">Book One</a></h3>
  <p class="star-rating Three"></p>
  <p class="price_color">£12.50</p>
  <p class="instock availability"><i></i> In stock</p>
</article>
<article class="product_pod">
  <h3><a href="../../../book-two_2/index.html" title="Book Two">Book Two</a></h3>
  <p class="star-rating Five"></p>
  <p class="price_color">£9.99</p>
  <p class="instock availability"><i></i> In stock</p>
</article>
<li class="next"><a href="page-2.html">next</a></li>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<ul class="breadcrumb">
  <li><a href="/">Home</a></li>
  <li><a href="/catalogue/category/books/mystery_3/">Books</a></li>
  <li><a href="/catalogue/category/books/mystery_3/">Mystery</a></li>
  <li class="active">Book One</li>
</ul>
<div class="product_main">
  <h1>Book One</h1>
  <p class="price_color">£12.50</p>
  <p class="star-rating Three"></p>
  <p class="availability"><i></i> In stock (17 available)</p>
</div>
<div id="product_description"></div>
<p>A short description.</p>
</body></html>
"""


class UrlValidationTests(unittest.TestCase):
    def test_allows_canonical_url(self) -> None:
        self.assertEqual(
            validate_start_url("https://books.toscrape.com/"),
            "https://books.toscrape.com/",
        )

    def test_rejects_unsafe_urls(self) -> None:
        candidates = [
            "http://books.toscrape.com/",
            "https://example.com/",
            "https://books.toscrape.com.evil.test/",
            "https://user:pass@books.toscrape.com/",
            "https://books.toscrape.com:8443/",
        ]
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(CrawlError):
                validate_start_url(candidate)

    def test_parameter_limits(self) -> None:
        with self.assertRaises(CrawlError):
            CrawlParams(max_pages=0)
        with self.assertRaises(CrawlError):
            CrawlParams(request_interval=11)


class ParserTests(unittest.TestCase):
    def test_listing_parser(self) -> None:
        page = parse_listing(
            LISTING_HTML,
            "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
        )
        self.assertEqual(len(page.items), 2)
        self.assertEqual(page.page_category, "Mystery")
        self.assertEqual(page.items[0].title, "Book One")
        self.assertEqual(page.items[0].price, "£12.50")
        self.assertEqual(page.items[0].rating, 3)
        self.assertTrue(page.items[0].detail_url.startswith("https://books.toscrape.com/"))
        self.assertEqual(
            page.next_url,
            "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html",
        )

    def test_detail_parser(self) -> None:
        detail = parse_detail(
            DETAIL_HTML,
            "https://books.toscrape.com/catalogue/book-one_1/index.html",
        )
        self.assertEqual(detail.title, "Book One")
        self.assertEqual(detail.category, "Mystery")
        self.assertEqual(detail.rating, 3)
        self.assertTrue(detail.availability.startswith("In stock"))
        self.assertEqual(detail.description, "A short description.")

    def test_antibot_detection(self) -> None:
        self.assertIn("403", detect_antibot("", 403))
        self.assertIn("captcha", detect_antibot('<div class="g-recaptcha"></div>').lower())
        self.assertIsNone(detect_antibot("<html><h1>Books</h1></html>"))


class StoreTests(unittest.TestCase):
    def test_insert_deduplicate_and_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = JobStore(root / "crawler.db")
            params = CrawlParams(max_pages=1)
            job_id = store.create_job(params, root / "job")
            record = {
                "title": "Book One",
                "price": "£12.50",
                "rating": 3,
                "availability": "In stock",
                "category": "Mystery",
                "detail_url": "https://books.toscrape.com/catalogue/book-one_1/index.html",
                "description": "Description",
                "source_page": "https://books.toscrape.com/",
                "scraped_at": "2026-11-17T00:00:00+00:00",
                "quality_flags": [],
            }
            self.assertTrue(store.add_item(job_id, record))
            self.assertFalse(store.add_item(job_id, record))
            self.assertEqual(len(store.items(job_id)), 1)
            store.add_failure(job_id, params.start_url, "test", "expected failure")
            job = store.get_job(job_id)
            self.assertEqual(job["failures_count"], 1)
            self.assertEqual(len(store.get_failures(job_id)), 1)


if __name__ == "__main__":
    unittest.main()
