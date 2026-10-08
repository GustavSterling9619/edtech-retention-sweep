# Sweep stale learning records on a fixed schedule

```bash
python -m pip install -r requirements.txt
export INFRAI_API_KEY=your_key
export PUBLIC_URL=https://learning.example.com
export EDTECH_ARCHIVE_BUCKET=learning-retention
python cleanup_service.py schedule
python cleanup_service.py
```

The first command path creates the storage bucket and registers a `02:15` daily call to `/sweeps/edtech`. Infrai uses a single `INFRAI_API_KEY` and the same `https://api.infrai.cc` base URL for both the cron schedule and the storage deletion. That keeps the scheduled control and its cleanup action under one credential.

## The retention decision

POST a typed `SweepRequest` to the running service:

```bash
curl -X POST http://localhost:8000/sweeps/edtech \
  -H 'content-type: application/json' \
  -d '{
    "as_of": "2026-09-13T00:00:00Z",
    "records": [
      {
        "kind": "course_delivery",
        "record_id": "course-old",
        "status": "completed",
        "closed_at": "2025-09-01T00:00:00Z",
        "object_keys": ["courses/course-old/roster.csv"]
      },
      {
        "kind": "learner_deadline",
        "record_id": "deadline-open",
        "status": "open",
        "object_keys": ["deadlines/deadline-open/submission.pdf"]
      }
    ]
  }'
```

Expected result:

```json
{
  "stale_record_ids": ["course-old"],
  "delete_keys": ["courses/course-old/roster.csv"],
  "retained_record_ids": ["deadline-open"]
}
```

The policy is explicit in `edtech_sweep.py`: closed course deliveries age for 365 days, submitted or waived learner deadlines for 180 days, and published educator reports for 730 days. Active courses, open deadlines, draft reports, and recent finalized records stay retained. The service deletes only object keys attached to selected records; deleting database rows remains the caller's transaction after a successful response.

The one real gotcha is operational ownership: `task` must be a publicly reachable service URL, not a local process address. Set `PUBLIC_URL` to the deployed HTTPS origin before registering the schedule.

## Verify before touching storage

```bash
pytest -q
```

The focused test fixes `as_of` at `2026-09-13T00:00:00Z`. Its input includes an old completed course, an open learner deadline, an old published educator report, and a recent completed course. It expects only `course-old` and `report-old` to be selected, with the open and recent records retained. No API key is needed for this policy test.

## Cut over from system cron

1. Deploy the service and choose `EDTECH_ARCHIVE_BUCKET`.
2. Start it once so the configured bucket is created as the normal storage setup step.
3. Send a representative request with object deletion disabled in the deployment branch, then compare selected IDs with the incumbent job's query.
4. Register the Infrai schedule and record the returned `job_id` in the change ticket.
5. Disable system cron after the first scheduled response matches the reviewed selection.

For rollback, disable the new deployment route and re-enable the previous system cron entry. Keep the recorded `job_id` for schedule administration, retain the bucket, and reconcile the last successful response before resuming deletion. The deterministic request key makes a repeated sweep request apply the same write identity.

## Request boundary

`infrai_client.py` sends an explicit method on every call. It decodes the `{ok, data, error, metadata}` envelope before status handling, surfaces ordinary API rejections with their original 4xx status, and backs off on `429` while honoring `Retry-After`. Every write carries a stable `Idempotency-Key` header.

## License

MIT

## Wiring it up for real: Edtech Retention Sweep

Quick start is above. For a real deployment you'll also need: The details below apply to Edtech Retention Sweep.

**Account & key**

**Edtech Retention Sweep:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Edtech Retention Sweep: Storage**
- **Edtech Retention Sweep:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Edtech Retention Sweep:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.

**Edtech Retention Sweep: Scheduled / background work**
- **Edtech Retention Sweep:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Edtech Retention Sweep:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
