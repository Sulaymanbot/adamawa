"""Aggregate statistics for the administrator dashboard (never per-voter choices)."""

from __future__ import annotations

from app.extensions import db
from app.models import Vote, Voter
from app.services import election_service


def summary() -> dict:
    by_status = dict(
        db.session.execute(
            db.select(Voter.verification_status, db.func.count(Voter.id)).group_by(Voter.verification_status)
        ).all()
    )
    elections = election_service.list_all()
    election_counts: dict[str, int] = {}
    for e in elections:
        election_counts[e.status] = election_counts.get(e.status, 0) + 1

    participation = []
    for e in elections:
        if e.status in {"open", "closed"}:
            cast = election_service.votes_cast(e.id)
            eligible = election_service.eligible_voter_count(e)
            participation.append(
                {
                    "election_id": e.id,
                    "title": e.title,
                    "status": e.status,
                    "phase": election_service.phase(e),
                    "votes_cast": cast,
                    "eligible_voters": eligible,
                    "turnout_percent": round(cast * 100 / eligible, 1) if eligible else None,
                    "results_published": e.results_published_at is not None,
                }
            )

    pending_actions = []
    if by_status.get("pending"):
        pending_actions.append({"type": "verify_voters", "count": by_status["pending"], "label": "Approve new voters"})
    for e in elections:
        if e.status == "closed" and e.results_published_at is None:
            pending_actions.append({"type": "publish_results", "election_id": e.id, "label": f"Publish results: {e.title}"})
        if e.status == "open" and election_service.phase(e) == "voting_ended":
            pending_actions.append(
                {
                    "type": "close_election",
                    "election_id": e.id,
                    "label": f"Close voting: {e.title}",
                }
            )

    return {
        "voters": {
            "total": sum(by_status.values()),
            "verified": by_status.get("verified", 0),
            "pending": by_status.get("pending", 0),
            "rejected": by_status.get("rejected", 0),
            "suspended": by_status.get("suspended", 0),
        },
        "elections": {"total": len(elections), "by_status": election_counts},
        "total_votes": db.session.execute(db.select(db.func.count(Vote.id))).scalar_one(),
        "participation": participation,
        "pending_actions": pending_actions,
        "open_elections": sum(1 for e in elections if e.status == "open"),
        "draft_or_scheduled": sum(1 for e in elections if e.status in {"draft", "scheduled"}),
    }
