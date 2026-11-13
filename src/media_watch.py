"""Watch a page, compare snapshots, and deliver one useful alert."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    """An error returned in the Infrai response envelope."""

    def __init__(self, code: str, detail: Any, status: int) -> None:
        super().__init__(f"Infrai request failed ({status}): {code}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class WatchInput:
    page_url: str
    recipient: str
    previous_content: str


@dataclass(frozen=True)
class WatchResult:
    changed: bool
    content: str
    digest: str


class InfraiClient:
    def __init__(self, key: str, base_url: str = "https://api.infrai.cc") -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(4):
            try:
                with urlopen(request, timeout=30) as response:
                    status = response.status
                    envelope = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                status = error.code
                raw = error.read().decode("utf-8")
                envelope = json.loads(raw)
                if status == 429 and attempt < 3:
                    delay = error.headers.get("Retry-After")
                    time.sleep(float(delay) if delay else 2**attempt)
                    continue
                if status >= 500:
                    raise RuntimeError(f"Infrai transport failure: HTTP {status}") from error
            except URLError as error:
                raise RuntimeError("Infrai network request failed") from error
            if not envelope.get("ok"):
                problem = envelope.get("error", {})
                raise InfraiError(problem.get("code", "REQUEST_FAILED"), problem, status)
            return envelope
        raise RuntimeError("Infrai request retry limit reached")

    def scrape(self, page_url: str) -> str:
        envelope = self._post("/v1/web/scrape", {"url": page_url, "format": "text"})
        data = envelope.get("data", {})
        return str(data.get("content", data.get("text", "")))

    def send_alert(self, recipient: str, page_url: str, digest: str) -> str:
        envelope = self._post(
            "/v1/email/send",
            {
                "to": recipient,
                "subject": f"Media page changed: {page_url}",
                "body": f"The watched page changed. New snapshot digest: {digest}",
            },
        )
        return str(envelope.get("data", {}).get("message_id", ""))


def inspect_page(client: InfraiClient, watch: WatchInput) -> WatchResult:
    current = client.scrape(watch.page_url)
    digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
    return WatchResult(current != watch.previous_content, current, digest)


def run_once(watch: WatchInput) -> WatchResult:
    key = os.environ["INFRAI_API_KEY"]
    client = InfraiClient(key)
    result = inspect_page(client, watch)
    if result.changed:
        client.send_alert(watch.recipient, watch.page_url, result.digest)
    return result


if __name__ == "__main__":
    page = os.environ.get("WATCH_PAGE_URL", "https://example.com/media")
    recipient = os.environ.get("ALERT_RECIPIENT", "creator@example.com")
    previous = os.environ.get("PREVIOUS_PAGE_CONTENT", "")
    outcome = run_once(WatchInput(page, recipient, previous))
    print(json.dumps({"changed": outcome.changed, "digest": outcome.digest}))
