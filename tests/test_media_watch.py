from src.media_watch import WatchInput, WatchResult, inspect_page


class StubClient:
    def __init__(self, content: str) -> None:
        self.content = content

    def scrape(self, page_url: str) -> str:
        return self.content


def test_changed_media_page_is_marked_for_alert() -> None:
    result = inspect_page(
        StubClient("episode 8"),
        WatchInput("https://media.example/stream", "creator@example.com", "episode 7"),
    )

    assert result == WatchResult(
        changed=True,
        content="episode 8",
        digest="bce0b2608911ae7e671097ab0d62533d71459208a60cc280bcf309cbc1fd02a4",
    )
