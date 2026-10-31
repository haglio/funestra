"""Harvest the funscripts people attach to their free-script topics on EroScripts.

    python tools/harvest_eroscripts.py [--corpus <dir>]

``<dir>/eroscripts/user_api_key.txt`` and ``user_api_client_id.txt`` hold a
Discourse user API key with read scope, authorized by the account's owner.
Scripts land in ``<dir>/eroscripts/scripts/``, named by topic and post rather
than by title; ``index.jsonl`` beside them says what each one was, and
``done_topics.txt`` is what a stopped run resumes from.  Standard library and
app_support only.
"""
from __future__ import annotations

import argparse
import html
import http.client
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from app_support import haglio_settings

logger = logging.getLogger(__name__)
_TIMEOUT_S = 60
# Added to whatever wait a 429 names, so the retry lands past the limit's edge
# rather than on it.
RETRY_GRACE_S = 1.0
_RETRIES = 6
# A request the network drops is asked again after each of these, then the
# run ends with the error: three quarters of an hour covers a router restart
# or the forum's nightly maintenance, and a run left for weeks meets both.
NETWORK_WAITS_S = (30.0, 60.0, 120.0, 300.0, 600.0, 900.0, 900.0)
_DEFAULT_WAIT_S = 60.0
_REDIRECTS = (301, 302, 303, 307, 308)
_MISSING = (403, 404)
# A topic or upload the forum will not hand over is skipped, not retried.
_GONE = (403, 404, 410, 422)
FORUM = "https://discuss.eroscripts.com"
# Where the forum keeps the files themselves.  A file is named by its SHA-1,
# which its short link spells in base 62, and filed under the first one to
# three characters of that name; which depth is not in the link, so a file is
# looked for at each, deepest first, since that is where most of them are.
FILE_HOST = "https://eroscripts-discourse.eroscripts.com"
_BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_FILE_DEPTHS = (4, 3, 2, 1)
FREE_SCRIPTS = "scripts/free-scripts/14"

_ATTACHMENT = re.compile(r'<a class="attachment" href="([^"]+)">([^<]*)</a>')
# A multi-axis script comes as one file per axis, named for the axis; only the
# main axis is wanted, which is the file named for nothing.
_OTHER_AXES = ("roll", "pitch", "twist", "sway", "surge", "vib", "raw")


class Attachment(NamedTuple):
    url: str
    name: str


def attachments_in(cooked: str) -> list[Attachment]:
    found = []
    for url, escaped in _ATTACHMENT.findall(cooked):
        name = html.unescape(escaped)
        if is_main_axis_script(name):
            found.append(Attachment(url, name))
    return found


def is_main_axis_script(name: str) -> bool:
    lowered = name.lower()
    if not lowered.endswith(".funscript"):
        return False
    stem = lowered.removesuffix(".funscript")
    return not any(stem.endswith("." + axis) for axis in _OTHER_AXES)


def file_addresses(short_url: str) -> list[str]:
    stem, _dot, extension = short_url.rsplit("/", 1)[-1].partition(".")
    number = 0
    for digit in stem:
        number = number * 62 + _BASE62.index(digit)
    name = f"{number:040x}.{extension}"
    return [
        f"{FILE_HOST}/original/{depth}X/" + "".join(f"{char}/" for char in name[:depth - 1]) + name
        for depth in _FILE_DEPTHS
    ]


class Forum:
    """The forum's JSON, one request at a time and never faster than *pace_s*."""

    def __init__(self, base_url: str, headers: dict[str, str], *,
                 opener: Callable = urllib.request.urlopen,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 pace_s: float = 1.0,
                 log: logging.Logger = logger) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers
        self._opener = opener
        self._sleep = sleep
        self._clock = clock
        self._pace_s = pace_s
        self._log = log
        self._last_request: float | None = None

    def get_json(self, path: str) -> dict:
        return json.loads(self._read(self._base_url + path, self._headers))

    def download(self, short_url: str) -> tuple[bytes, str]:
        """The attachment the forum's short link leads to, and where it really was.

        The file host is tried first at each address the link can mean, and
        the forum is asked for the redirect only when none of them has it; the
        key is the forum's business, so a file is always fetched without it.
        """
        plain = {"User-Agent": self._headers.get("User-Agent", "")}
        for where in file_addresses(short_url):
            try:
                return self._read(where, plain, paced=False), where
            except urllib.error.HTTPError as error:
                if error.code not in _MISSING:
                    raise
        try:
            return self._read(self._base_url + short_url, self._headers), self._base_url + short_url
        except urllib.error.HTTPError as error:
            if error.code not in _REDIRECTS:
                raise
            where = error.headers.get("Location")
        return self._read(where, plain, paced=False), where

    def _read(self, url: str, headers: dict[str, str], *, paced: bool = True) -> bytes:
        request = urllib.request.Request(url, headers=headers)
        limited = 0
        waits_left = list(NETWORK_WAITS_S)
        while True:
            if paced:
                self._wait_the_pace()
            try:
                with self._opener(request, timeout=_TIMEOUT_S) as response:
                    return response.read()
            except (OSError, http.client.HTTPException) as error:
                if _rate_limited(error):
                    limited += 1
                    if limited == _RETRIES:
                        raise RuntimeError(
                            f"{url}: still rate limited after {_RETRIES} attempts") from error
                    wait = _wait_named_by(error) + RETRY_GRACE_S
                    self._log.info("rate limited at %s: waiting %.0f s", url, wait)
                elif _may_be_asked_again(error) and waits_left:
                    wait = waits_left.pop(0)
                    self._log.info("no answer from %s (%s): waiting %.0f s", url, error, wait)
                else:
                    raise
            self._sleep(wait)

    def _wait_the_pace(self) -> None:
        now = self._clock()
        if self._last_request is not None:
            owed = self._pace_s - (now - self._last_request)
            if owed > 0:
                self._sleep(owed)
        self._last_request = self._clock()


def _rate_limited(error: Exception) -> bool:
    return isinstance(error, urllib.error.HTTPError) and error.code == 429


def _may_be_asked_again(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= 500
    return True


def _wait_named_by(error: urllib.error.HTTPError) -> float:
    header = error.headers.get("Retry-After")
    if header and header.strip().isdigit():
        return float(header)
    try:
        return float(json.loads(error.read())["extras"]["wait_seconds"])
    except (ValueError, KeyError, TypeError, OSError):
        return _DEFAULT_WAIT_S


class Store:
    """The scripts already taken, and the topics already looked at."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(parents=True, exist_ok=True)
        self._done_path = self.root / "done_topics.txt"
        self._index_path = self.root / "index.jsonl"
        self._done = {int(line) for line in _lines(self._done_path)}
        self._uploads = {json.loads(line)["url"] for line in _lines(self._index_path)}

    def is_done(self, topic_id: int) -> bool:
        return topic_id in self._done

    def has_upload(self, url: str) -> bool:
        return url in self._uploads

    def save(self, topic_id: int, post_number: int, ordinal: int, body: bytes,
             record: dict) -> Path:
        name = f"t{topic_id}_p{post_number}_{ordinal}.funscript"
        (self.scripts / name).write_bytes(body)
        line = json.dumps({"file": name, "topic": topic_id, "post": post_number, **record,
                           "bytes": len(body)}, ensure_ascii=False)
        with self._index_path.open("a", encoding="utf-8") as index:
            index.write(line + "\n")
        self._uploads.add(record["url"])
        return self.scripts / name

    def finish(self, topic_id: int) -> None:
        with self._done_path.open("a", encoding="utf-8") as done:
            done.write(f"{topic_id}\n")
        self._done.add(topic_id)


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def harvest(forum, store: Store, *, log: logging.Logger, category: str = FREE_SCRIPTS,
            max_topics: int | None = None) -> int:
    """Walk *category* newest first, taking every topic the store has not seen."""
    taken = 0
    page_path: str | None = f"/c/{category}.json?page=0"
    while page_path:
        topic_list = forum.get_json(page_path)["topic_list"]
        for topic in topic_list["topics"]:
            if store.is_done(topic["id"]):
                continue
            harvest_topic(forum, store, topic["id"], log=log)
            taken += 1
            if max_topics is not None and taken >= max_topics:
                return taken
        page_path = _json_path(topic_list.get("more_topics_url"))
    return taken


def _json_path(more_topics_url: str | None) -> str | None:
    if not more_topics_url:
        return None
    path, _, query = more_topics_url.partition("?")
    return f"{path}.json?{query}" if query else f"{path}.json"


def harvest_topic(forum, store: Store, topic_id: int, *, log: logging.Logger) -> None:
    try:
        topic = forum.get_json(f"/t/{topic_id}.json")
    except urllib.error.HTTPError as error:
        if error.code not in _GONE:
            raise
        log.warning("topic %s: HTTP %s, skipped", topic_id, error.code)
        store.finish(topic_id)
        return
    for post in topic["post_stream"]["posts"]:
        for ordinal, attachment in enumerate(attachments_in(post["cooked"]), 1):
            if store.has_upload(attachment.url):
                continue
            try:
                body, where = forum.download(attachment.url)
            except urllib.error.HTTPError as error:
                if error.code not in _GONE:
                    raise
                log.warning("topic %s: %s HTTP %s, skipped", topic_id, attachment.url, error.code)
                continue
            store.save(topic_id, post["post_number"], ordinal, body, {
                "url": attachment.url, "where": where, "name": attachment.name,
                "title": topic.get("title", ""), "tags": _tag_names(topic.get("tags", [])),
                "created_at": topic.get("created_at", ""),
            })
            log.info("topic %s post %s: %s bytes", topic_id, post["post_number"], len(body))
    store.finish(topic_id)


def _tag_names(tags: list) -> list[str]:
    return [tag["name"] if isinstance(tag, dict) else str(tag) for tag in tags]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _forum_for(corpus: Path, pace_s: float) -> Forum:
    secrets = corpus / "eroscripts"
    headers = {
        "User-Api-Key": (secrets / "user_api_key.txt").read_text(encoding="utf-8").strip(),
        "User-Api-Client-Id": (secrets / "user_api_client_id.txt").read_text(encoding="utf-8").strip(),
        "User-Agent": "Fun Time funscript corpus/0.1",
        "Accept": "application/json",
    }
    return Forum(FORUM, headers, opener=urllib.request.build_opener(_NoRedirect()).open,
                 pace_s=pace_s)


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--category", default=FREE_SCRIPTS)
    parser.add_argument("--pace", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--max-topics", type=int, default=None)
    args = parser.parse_args(argv)
    if args.corpus is None:
        args.corpus = Path(haglio_settings.value("funscript_corpus_dir"))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    root = args.corpus / "eroscripts"
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(root / "harvest.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)])
    log = logging.getLogger("harvest")
    taken = harvest(_forum_for(args.corpus, args.pace), Store(root), log=log,
                    category=args.category, max_topics=args.max_topics)
    log.info("done: %s topics this run", taken)
    return 0


if __name__ == "__main__":
    sys.exit(main())
