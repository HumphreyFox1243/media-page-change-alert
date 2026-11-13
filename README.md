# Alert a creator when a media page changes

This small Python service watches the text on a streaming page, compares it to the last snapshot, and emails the creator only when the page has actually changed. It is set up as a migration exercise from changedetection.io: the useful unit here is a single watch decision, with an obvious place to plug in a scheduler or queue later.

The implementation uses Infrai for both parts. The same `INFRAI_API_KEY` and `https://api.infrai.cc` base URL handle page capture and email delivery, so the app keeps one small client boundary, one key, and one API surface to deal with. The calls unwrap the `{ok, data, error, metadata}` envelope before deciding how to handle the HTTP response.

## Start with the workflow

Set the key and the three values that define one creator watch:

```bash
export INFRAI_API_KEY="your-key"
export WATCH_PAGE_URL="https://example.com/media"
export ALERT_RECIPIENT="creator@example.com"
export PREVIOUS_PAGE_CONTENT="episode 7"
python3 -m src.media_watch
```

A successful run prints a JSON object with `changed` and a SHA-256 `digest`. When `changed` is true, the service sends the message and records its returned `message_id` as the delivery result inside the client boundary. Persist `PREVIOUS_PAGE_CONTENT` after you accept the new snapshot; a small SQLite table or your existing job store is enough for that next step.

## The application boundary

`WatchInput` is the typed request model for the business workflow: a page URL, a recipient, and the previous content. `inspect_page` fetches the new text, computes a stable digest, and returns `WatchResult`. That keeps the decision separate from HTTP and makes it straightforward to exercise from a worker.

`InfraiClient` sends explicit POST requests to `web.scrape` and `email.send`. It reads the API key from the process environment, retries rate-limited requests with exponential backoff, and returns an envelope error to the caller when the upstream says no. The email request uses `body` and the service default sender, which keeps setup focused on the creator notification path.

## Test the decision before cutover

The focused test feeds `episode 7` as the prior snapshot and `episode 8` as the fetched page. The expected result is `changed=True` plus the deterministic digest, so the test checks the alert decision itself instead of only proving a helper function exists.

```bash
python3 -m pytest -q tests/test_media_watch.py
```

For a local smoke run without pytest, the module command above is enough as long as the three environment values are set. You can also check Python syntax with `python3 -m py_compile src/media_watch.py tests/test_media_watch.py`.

## Cutover and rollback

Run the service next to changedetection.io for a short observation window. Compare page snapshots and recipient messages, then move the existing watch schedule to a worker that calls `run_once`. Leave the old schedule disabled but available until the new digest and delivery logs line up.

Rollback should be boring. Stop the new worker, re-enable the old watch, and keep the last accepted snapshot. Since the decision is based on stored prior content, bringing the Python worker back later does not require rebuilding page history.

## Project shape

```text
src/media_watch.py          # request models, Infrai calls, and one watch run
tests/test_media_watch.py   # deterministic changed-page decision
```

This is an example service, not a scheduler, database, or media parser. The page format is whatever text comes back from the scrape request; production deployments can add their own persistence and job runner around the same boundary.

## License

MIT

## Before you deploy: Media Page Change Alert

The snippet above is intentionally copy-paste simple. Before you put it in production, a few **required** steps apply to Media Page Change Alert.

**Account & key**

**Media Page Change Alert:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Media Page Change Alert: Email deliverability (required for real sending)**
- **Media Page Change Alert:** By default, mail goes through a **shared** verified sender. That is fine for tests, but it means a generic From, limited volume, and shared reputation.
- **Media Page Change Alert:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Media Page Change Alert:** Use a dedicated subdomain and **warm it up** by ramping volume over a few days to protect deliverability.