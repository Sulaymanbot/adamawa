"""Result computation.

Ballots are decrypted only here, only for elections whose results are
published, and only to produce aggregate per-race totals. Individual
plaintext ballots are never returned, stored or logged.

Tie handling: if two or more candidates share the highest total in a race the
race outcome is reported as "tie" and no winner is declared; resolution is an
administrative matter outside the system.

Small-count protection: races with fewer than RESULTS_MIN_RACE_VOTES valid
votes have their per-candidate totals withheld, so a published result cannot
be combined with participation data to infer an individual ballot.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from flask import current_app

from app.errors import APIError
from app.extensions import db
from app.models import Candidate, Election, LocalGovernmentArea, Vote
from app.services import audit_service, crypto_service, election_service

log = logging.getLogger("app.results")


def tally(election: Election) -> dict:
    candidates = {c.id: c for c in db.session.execute(db.select(Candidate).filter_by(election_id=election.id)).scalars()}
    counts: Counter[int] = Counter()
    invalid = 0
    total_rows = 0
    for vote in db.session.execute(db.select(Vote).filter_by(election_id=election.id).execution_options(yield_per=500)).scalars():
        total_rows += 1
        try:
            payload = crypto_service.decrypt_ballot(
                election.id, vote.receipt_reference, vote.payload_nonce, vote.encrypted_vote_payload, vote.integrity_hash
            )
        except (crypto_service.BallotDecryptionError, ValueError):
            invalid += 1
            continue
        candidate = candidates.get(payload.get("c"))
        if candidate is None or candidate.lga_id != payload.get("l"):
            invalid += 1
            continue
        counts[candidate.id] += 1
    if invalid:
        log.warning("tally_invalid_ballots", extra={"election": election.id, "invalid": invalid})
        audit_service.record(
            "results.invalid_ballots",
            f"{invalid} ballot(s) failed integrity checks for election #{election.id}",
            entity_type="election",
            entity_id=election.id,
        )
    return {"counts": counts, "invalid": invalid, "total_rows": total_rows, "candidates": candidates}


def compute(election: Election) -> dict:
    raw = tally(election)
    counts, candidates = raw["counts"], raw["candidates"]
    threshold = current_app.config.get("RESULTS_MIN_RACE_VOTES", 3)

    by_lga: dict[int, list[Candidate]] = defaultdict(list)
    for c in candidates.values():
        if c.status == "active" or counts[c.id]:
            by_lga[c.lga_id].append(c)
    lga_names = {
        lga.id: lga.name
        for lga in db.session.execute(db.select(LocalGovernmentArea).where(LocalGovernmentArea.id.in_(list(by_lga)))).scalars()
    }

    races = []
    for lga_id in sorted(by_lga, key=lambda i: lga_names.get(i, "")):
        rows = by_lga[lga_id]
        total = sum(counts[c.id] for c in rows)
        race = {"lga": {"id": lga_id, "name": lga_names.get(lga_id)}, "total_valid_votes": total}
        if total == 0:
            race.update(outcome="no_votes", candidates=[_row(c, 0, total) for c in rows], winner=None)
        elif total < threshold:
            race.update(
                outcome="withheld",
                candidates=[_row(c, None, total) for c in rows],
                winner=None,
                note=(
                    f"Fewer than {threshold} votes were cast in this race, so per-candidate totals "
                    "are withheld to protect ballot secrecy."
                ),
            )
        else:
            ranked = sorted(rows, key=lambda c: (-counts[c.id], c.full_name))
            top = counts[ranked[0].id]
            leaders = [c for c in ranked if counts[c.id] == top]
            race["candidates"] = [_row(c, counts[c.id], total) for c in ranked]
            if len(leaders) > 1:
                race.update(
                    outcome="tie",
                    winner=None,
                    note="Tie: two or more candidates have the highest total. Resolution happens outside this system.",
                )
            else:
                race.update(outcome="winner", winner={"id": leaders[0].id, "full_name": leaders[0].full_name})
        races.append(race)

    eligible = election_service.eligible_voter_count(election)
    valid = sum(counts.values())
    return {
        "election": election_service.serialize(election),
        "is_simulated": True,
        "summary": {
            "ballots_cast": raw["total_rows"],
            "valid_votes": valid,
            "invalid_ballots": raw["invalid"],
            "eligible_voters": eligible,
            "turnout_percent": round(raw["total_rows"] * 100 / eligible, 1) if eligible else None,
        },
        "races": races,
        "disclaimer": "SIMULATED RESULTS from an academic prototype. Not an official election result.",
    }


def _row(c: Candidate, votes: int | None, total: int) -> dict:
    return {
        "id": c.id,
        "full_name": c.full_name,
        "party_affiliation": c.party_affiliation,
        "votes": votes,
        "percentage": round(votes * 100 / total, 1) if votes is not None and total else (None if votes is None else 0.0),
    }


def results_for_public(election_id: int) -> dict:
    election = db.session.get(Election, election_id)
    if election is None or election.status in {"draft"}:
        raise APIError(404, "not_found", "Election not found.")
    if not election_service.results_visible(election):
        raise APIError(403, "results_not_published", "Results for this election have not been published yet.")
    return compute(election)
