"""Weekly recruiter digest — Friday EOD email per active user.

Reads `badge_view_stats_user` for the past 7 days, computes per-recruiter
"you prevented N duplicate captures" stats, and emails each user a small
personalised digest. Two goals:

  1. Make the extension's value visible (recruiters love seeing their
     own number).
  2. Nudge wrong-match button adoption by adding a one-line CTA
     explaining how flagging mismatches improves the engine.

Called from `services.lifecycle` via APScheduler — Fridays 11:30 IST
(06:00 UTC). Safe to call ad-hoc via the admin endpoint
`POST /api/admin/badge-audit/_/digest/run-now`.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from config import db
from services.email_service import send_email

logger = logging.getLogger(__name__)

ADMIN_BCC = "admin@vhc.in"   # always copied for visibility


def _minutes_saved(shown: int) -> int:
    """Each duplicate-capture prevented saves ~2 min of recruiter time.
    Round to the nearest minute for a clean number."""
    return shown * 2


def _digest_html(recruiter: Dict[str, Any]) -> str:
    name = recruiter.get("name") or (recruiter["user_email"] or "").split("@")[0].title()
    shown = recruiter["shown"]
    scanned = recruiter["scanned"]
    minutes = _minutes_saved(shown)
    dedup_rate = round(100.0 * shown / max(scanned, 1), 1)
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
      <h2 style="color:#059669;margin-bottom:6px">Hi {name},</h2>
      <p style="font-size:15px;line-height:1.5">
        Here's what the VHC extension did for you this week:
      </p>

      <div style="background:linear-gradient(135deg,#ecfdf5,#d1fae5);border-radius:12px;padding:20px;margin:18px 0">
        <div style="font-size:13px;color:#065f46;font-weight:500">Duplicate captures prevented</div>
        <div style="font-size:42px;font-weight:700;color:#059669;line-height:1.1;margin-top:4px">{shown:,}</div>
        <div style="font-size:13px;color:#047857;margin-top:6px">
          ≈ <strong>{minutes:,} minutes</strong> ({minutes // 60}h {minutes % 60}m) of capture time saved
        </div>
      </div>

      <table style="width:100%;font-size:14px;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#6b7280">Candidates scanned</td><td style="text-align:right;font-weight:600">{scanned:,}</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">Already in bank</td><td style="text-align:right;font-weight:600">{shown:,} ({dedup_rate}%)</td></tr>
        <tr><td style="padding:6px 0;color:#6b7280">Net-new to capture</td><td style="text-align:right;font-weight:600">{scanned - shown:,}</td></tr>
      </table>

      <div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:14px 16px;margin:20px 0;border-radius:6px">
        <div style="font-size:13px;font-weight:600;color:#92400e;margin-bottom:4px">Help us get smarter</div>
        <div style="font-size:13px;color:#78350f;line-height:1.5">
          See a green badge on someone who's clearly <em>not</em> the same person? Click the small red
          <strong>✗ Wrong match?</strong> chip on the card. It takes one click, never shows a popup, and
          directly trains the matching engine. Even 5 flags a week make a measurable difference.
        </div>
      </div>

      <p style="font-size:12px;color:#9ca3af;margin-top:24px">
        VHC Talent OS · weekly digest · sent Fridays · scanned data resets at midnight IST
      </p>
    </div>
    """


async def build_weekly_digest_rows(days: int = 7) -> List[Dict[str, Any]]:
    """Return one row per active recruiter for the past `days`. Skips users
    with 0 scans (no point in mailing them about nothing)."""
    horizon = (date.today() - timedelta(days=days - 1)).isoformat()
    pipeline = [
        {"$match": {"day": {"$gte": horizon}}},
        {"$group": {
            "_id": "$user_email",
            "shown":   {"$sum": "$shown_count"},
            "scanned": {"$sum": "$scanned_count"},
            "user_id": {"$first": "$user_id"},
        }},
        {"$match": {"scanned": {"$gt": 0}}},
        {"$sort":  {"shown": -1}},
    ]
    try:
        agg = await db.badge_view_stats_user.aggregate(pipeline).to_list(200)
    except Exception as e:
        logger.exception(f"[WeeklyDigest] aggregation failed: {e}")
        return []
    out: List[Dict[str, Any]] = []
    for r in agg:
        email = r.get("_id")
        if not email:
            continue
        u = await db.users.find_one({"email": email}, {"_id": 0, "name": 1, "is_active": 1}) or {}
        if u.get("is_active") is False:
            continue
        out.append({
            "user_email": email,
            "name":       u.get("name"),
            "shown":      r["shown"],
            "scanned":    r["scanned"],
        })
    return out


async def send_weekly_digest(dry_run: bool = False) -> Dict[str, Any]:
    """Send the weekly digest to every active recruiter. When dry_run is
    True, returns the would-be rows without sending."""
    rows = await build_weekly_digest_rows(days=7)
    if dry_run:
        return {"would_send": len(rows), "rows": rows}
    sent = 0
    failed = 0
    started = datetime.now(timezone.utc).isoformat()
    for r in rows:
        try:
            res = await send_email(
                recipient_email=r["user_email"],
                subject=f"You prevented {r['shown']:,} duplicate captures this week",
                html_content=_digest_html(r),
            )
            if res.get("status") in ("sent", "queued", "skipped"):
                sent += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"[WeeklyDigest] send to {r['user_email']} failed: {e}")
    # Persistent log so admins can see when it ran + how many landed
    await db.weekly_digest_runs.insert_one({
        "started_at": started,
        "ended_at":   datetime.now(timezone.utc).isoformat(),
        "rows":       len(rows),
        "sent":       sent,
        "failed":     failed,
    })
    return {"rows": len(rows), "sent": sent, "failed": failed}
