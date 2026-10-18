"""Election state transitions, voting window, eligibility and results visibility."""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Election, utcnow
from app.services import election_service as es


@pytest.mark.parametrize(
    ("status", "action", "allowed"),
    [
        ("draft", "schedule", True),
        ("draft", "open", True),
        ("draft", "close", False),
        ("scheduled", "open", True),
        ("scheduled", "unschedule", True),
        ("open", "close", True),
        ("open", "schedule", False),
        ("open", "cancel", True),
        ("closed", "open", False),
        ("closed", "archive", True),
        ("closed", "cancel", False),
        ("archived", "open", False),
        ("cancelled", "open", False),
        ("cancelled", "archive", True),
    ],
)
def test_transition_table(status, action, allowed):
    assert es.can_transition(status, action) is allowed


def make(status="open", start=-1, end=1, published=None):
    now = utcnow()
    return Election(
        title="x",
        type="lg_chairmanship",
        scope="all_lgas",
        status=status,
        start_at=now + timedelta(hours=start),
        end_at=now + timedelta(hours=end),
        results_published_at=published,
        created_by=1,
    )


def test_voting_open_requires_status_and_window():
    assert es.voting_open(make())
    assert not es.voting_open(make(status="scheduled"))
    assert not es.voting_open(make(start=1, end=2))  # not started
    assert not es.voting_open(make(start=-2, end=-1))  # ended
    assert not es.voting_open(make(status="closed"))


def test_phase():
    assert es.phase(make()) == "voting_open"
    assert es.phase(make(start=1, end=2)) == "opening_soon"
    assert es.phase(make(start=-2, end=-1)) == "voting_ended"
    assert es.phase(make(status="draft")) == "draft"


def test_results_visible_only_when_closed_and_published():
    now = utcnow()
    assert not es.results_visible(make(status="open", published=now))
    assert not es.results_visible(make(status="closed"))
    assert es.results_visible(make(status="closed", published=now - timedelta(minutes=1)))
    assert not es.results_visible(make(status="closed", published=now + timedelta(hours=1))), "scheduled publication"
    assert es.results_visible(make(status="archived", published=now - timedelta(minutes=1)))


def test_eligibility(world):
    e = world["election"]
    v = world["voters"]
    assert es.eligibility(e, v["yn1"]) == (True, None)
    assert es.eligibility(e, v["pending"]) == (False, "not_verified")
    assert es.eligibility(e, v["song"]) == (False, "no_candidates")
    assert es.eligibility(e, None) == (False, "not_a_voter")
    v["yn2"].user.status = "suspended"
    assert es.eligibility(e, v["yn2"]) == (False, "account_inactive")


def test_single_lga_scope(world):
    e = world["election"]
    yola_north = world["lgas"]["Yola North"].id
    e.scope = "single_lga"
    e.lga_id = yola_north
    db.session.commit()
    assert es.eligibility(e, world["voters"]["yn1"])[0]
    assert es.eligibility(e, world["voters"]["ys1"]) == (False, "out_of_scope")


def test_inactive_candidates_not_on_ballot(world):
    e = world["election"]
    world["candidates"]["num_a"].status = "inactive"
    db.session.commit()
    assert es.eligibility(e, world["voters"]["numan"]) == (False, "no_candidates")
    names = [c.full_name for c in es.active_candidates_for(e, world["lgas"]["Yola North"].id)]
    assert names == ["Alpha Candidate", "Bravo Candidate"]


def test_db_check_constraint_rejects_bad_status(world):
    from sqlalchemy.exc import IntegrityError

    world["election"].status = "hacked"
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_timestamps_have_whole_seconds_for_mysql():
    """MySQL DATETIME rounds fractional seconds; a publish time rounded up into the
    future would hide just-published results. Timestamps must be whole seconds."""
    from app.schemas import to_utc_naive

    assert utcnow().microsecond == 0
    from datetime import UTC, datetime

    assert to_utc_naive(datetime(2026, 1, 1, 9, 0, 0, 999999, tzinfo=UTC)).microsecond == 0
