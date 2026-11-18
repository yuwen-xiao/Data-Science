#!/usr/bin/env python3
"""Fetch and archive lightweight metadata/excerpts for the PCA source list."""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import requests
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
RAW = SOURCES / "raw"
RAW.mkdir(parents=True, exist_ok=True)

URLS = [
    {
        "id": "sklearn_pca",
        "kind": "official_docs",
        "url": "https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html",
    },
    {
        "id": "sklearn_decomposition",
        "kind": "official_docs",
        "url": "https://scikit-learn.org/stable/modules/decomposition.html#pca",
    },
    {
        "id": "geeksforgeeks_pca",
        "kind": "blog",
        "url": "https://www.geeksforgeeks.org/data-analysis/principal-component-analysis-pca/",
    },
    {
        "id": "shlens_tutorial",
        "kind": "paper",
        "url": "https://arxiv.org/abs/1404.1100",
    },
    {
        "id": "csdn_pca",
        "kind": "blog",
        "url": "https://blog.csdn.net/qq_54700138/article/details/146046975",
    },
    {
        "id": "uci_wine",
        "kind": "dataset",
        "url": "https://archive.ics.uci.edu/dataset/109/wine",
    },
]


def clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
    )

    records = []
    for item in URLS:
        record = {**item, "retrieved_on": date.today().isoformat()}
        try:
            response = session.get(item["url"], timeout=30)
            record["status_code"] = response.status_code
            response.raise_for_status()
            document = html.fromstring(response.text)
            title = clean_space(document.xpath("string(//title)"))
            description = ""
            for xpath in (
                "string(//meta[@name='description']/@content)",
                "string(//meta[@property='og:description']/@content)",
            ):
                description = clean_space(document.xpath(xpath))
                if description:
                    break
            text = clean_space(document.text_content())
            record.update({"title": title, "description": description})
            (RAW / f"{item['id']}.txt").write_text(
                f"TITLE: {title}\nURL: {item['url']}\nRETRIEVED: {record['retrieved_on']}\n\n{text[:12000]}\n",
                encoding="utf-8",
            )
        except Exception as exc:  # Keep the source record even if a page blocks us.
            record["error"] = str(exc)
        records.append(record)
        time.sleep(1.0)

    (SOURCES / "crawl_log.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
