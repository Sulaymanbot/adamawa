"""Demo data. Everything created here is fictional and labelled as demo data.

The 21 LGA names are the officially listed LGAs of Adamawa State. Wards and
polling units are NOT real: they are generated placeholders labelled "DEMO".
Demo voter identities, phone numbers and IDs are fictional.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from app.extensions import db
from app.models import (
    Admin,
    Candidate,
    Election,
    LocalGovernmentArea,
    PollingUnit,
    User,
    Voter,
    Ward,
    utcnow,
)
from app.security.identifiers import hash_voter_id
from app.security.passwords import hash_password

ADAMAWA_LGAS = [
    ("Demsa", "DEM"),
    ("Fufore", "FUF"),
    ("Ganye", "GAN"),
    ("Gayuk", "GAY"),
    ("Gombi", "GOM"),
    ("Grie", "GRI"),
    ("Hong", "HON"),
    ("Jada", "JAD"),
    ("Lamurde", "LAM"),
    ("Madagali", "MAD"),
    ("Maiha", "MAI"),
    ("Mayo-Belwa", "MAY"),
    ("Michika", "MIC"),
    ("Mubi North", "MBN"),
    ("Mubi South", "MBS"),
    ("Numan", "NUM"),
    ("Shelleng", "SHE"),
    ("Song", "SON"),
    ("Toungo", "TOU"),
    ("Yola North", "YLN"),
    ("Yola South", "YLS"),
]
WARDS_PER_LGA = 2
UNITS_PER_WARD = 2

DEMO_LGAS = ["Yola North", "Yola South", "Mubi North", "Numan"]
DEMO_PARTIES = [
    "Demo Progressive Party (DPP)",
    "Simulated Unity Alliance (SUA)",
    "Mock People's Congress (MPC)",
]
FIRST_NAMES = [
    "Aisha",
    "Musa",
    "Grace",
    "Ibrahim",
    "Fatima",
    "John",
    "Halima",
    "Daniel",
    "Zainab",
    "Peter",
    "Hauwa",
    "Samuel",
    "Amina",
    "Joseph",
    "Maryam",
    "Yakubu",
    "Esther",
    "Bello",
    "Ruth",
    "Umar",
    "Rakiya",
    "Emmanuel",
    "Hadiza",
    "Michael",
]
SURNAMES = [
    "Abubakar",
    "Bitrus",
    "Danjuma",
    "Garba",
    "Haruna",
    "Ishaku",
    "Jibrin",
    "Kwaji",
    "Lawan",
    "Mohammed",
    "Nuhu",
    "Obadiah",
    "Pwamwi",
    "Saidu",
    "Tizhe",
    "Usman",
    "Vandi",
    "Wakili",
    "Yohanna",
    "Zira",
    "Adamu",
    "Buba",
    "Chiroma",
    "Dauda",
]
CANDIDATE_NAMES = {
    "Yola North": ["Abdullahi Demo-Bakari", "Christiana Sample-Yohanna", "Hamidu Placeholder-Sali"],
    "Yola South": ["Ladi Fictional-Musa", "Bashir Testcase-Umar", "Comfort Mockup-Elijah"],
    "Mubi North": ["Yusuf Example-Tumba", "Rahila Dummy-Garba", "Ezekiel Simulated-Ali"],
    "Numan": ["Saratu Prototype-Bello", "Kefas Demo-Ishaya", "Asabe Specimen-Nuhu"],
}


def seed_locations() -> dict[str, LocalGovernmentArea]:
    lgas: dict[str, LocalGovernmentArea] = {}
    for name, code in ADAMAWA_LGAS:
        lga = db.session.execute(db.select(LocalGovernmentArea).filter_by(code=code)).scalar_one_or_none()
        if lga is None:
            lga = LocalGovernmentArea(name=name, code=code, active=True)
            db.session.add(lga)
            db.session.flush()
            for w in range(1, WARDS_PER_LGA + 1):
                ward = Ward(lga_id=lga.id, name=f"DEMO Ward {w} ({name})", code=f"{code}-W{w:02d}")
                db.session.add(ward)
                db.session.flush()
                for p in range(1, UNITS_PER_WARD + 1):
                    db.session.add(
                        PollingUnit(
                            ward_id=ward.id,
                            name=f"DEMO Polling Unit {p} – Ward {w} ({name})",
                            code=f"{code}-W{w:02d}-PU{p:03d}",
                        )
                    )
        lgas[name] = lga
    db.session.flush()
    return lgas


def create_admin(email: str, password: str, full_name: str = "Demo Electoral Officer") -> User:
    user = User(role="admin", email=email.strip().lower(), phone=None, password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    db.session.add(Admin(user_id=user.id, full_name=full_name))
    db.session.flush()
    return user


def create_voter(
    *, email, phone, voter_id, first_name, surname, lga, ward, polling_unit, password_hash, status="verified", verified_by=None
):
    user = User(role="voter", email=email, phone=phone, password_hash=password_hash)
    voter = Voter(
        user=user,
        voter_id_hash=hash_voter_id(voter_id),
        voter_id_last4=voter_id[-4:],
        surname=surname,
        first_name=first_name,
        lga_id=lga.id,
        ward_id=ward.id,
        polling_unit_id=polling_unit.id,
        verification_status=status,
        verified_by=verified_by if status == "verified" else None,
        verified_at=utcnow() if status == "verified" else None,
        verification_reason="DEMO: registration details could not be matched" if status == "rejected" else None,
    )
    db.session.add_all([user, voter])
    db.session.flush()
    return voter


def seed_demo(*, admin_email: str, admin_password: str, voter_password: str, voter_count: int = 24) -> dict:
    """Create demo locations, one admin, demo voters and a demo election."""
    lgas = seed_locations()
    if db.session.execute(db.select(User).filter_by(email=admin_email.lower())).scalar_one_or_none():
        raise RuntimeError("Demo data already exists. Run `flask reset-demo --yes` first to start over.")
    admin = create_admin(admin_email, admin_password)

    shared_hash = hash_password(voter_password)
    statuses = ["verified"] * (voter_count - 4) + ["pending", "pending", "pending", "rejected"]
    voters = []
    for i in range(voter_count):
        lga = lgas[DEMO_LGAS[i % len(DEMO_LGAS)]]
        ward = lga.wards[i % WARDS_PER_LGA]
        pu = ward.polling_units[(i // WARDS_PER_LGA) % UNITS_PER_WARD]
        voters.append(
            create_voter(
                email=f"voter{i + 1:02d}@example.com",
                phone=f"+23480100{i + 1:05d}",
                voter_id=f"DEMOAD{i + 1:010d}",
                first_name=FIRST_NAMES[i % len(FIRST_NAMES)],
                surname=SURNAMES[i % len(SURNAMES)],
                lga=lga,
                ward=ward,
                polling_unit=pu,
                password_hash=shared_hash,
                status=statuses[i],
                verified_by=admin.id,
            )
        )

    election = create_demo_election(admin.id, lgas)
    draft = Election(
        title="Yola North Councillorship Election (SIMULATED – draft)",
        type="councillorship",
        description="Draft single-LGA election used to demonstrate scoping. Demo data only.",
        scope="single_lga",
        lga_id=lgas["Yola North"].id,
        start_at=utcnow() + timedelta(days=14),
        end_at=utcnow() + timedelta(days=14, hours=8),
        status="draft",
        created_by=admin.id,
    )
    db.session.add(draft)
    db.session.commit()
    return {"admin": admin, "voters": voters, "election": election}


def create_demo_election(admin_id: int, lgas: dict[str, LocalGovernmentArea]) -> Election:
    start = utcnow() + timedelta(days=1)
    election = Election(
        title="2026 Adamawa LG Chairmanship Election (SIMULATED)",
        type="lg_chairmanship",
        description=(
            "A simulated local government chairmanship election for demonstration. Candidates, parties and results are fictional."
        ),
        scope="all_lgas",
        lga_id=None,
        start_at=start,
        end_at=start + timedelta(hours=10),
        status="scheduled",
        created_by=admin_id,
    )
    db.session.add(election)
    db.session.flush()
    for lga_name, names in CANDIDATE_NAMES.items():
        for name, party in zip(names, DEMO_PARTIES, strict=True):
            db.session.add(
                Candidate(
                    election_id=election.id,
                    lga_id=lgas[lga_name].id,
                    full_name=name,
                    party_affiliation=party,
                    manifesto_summary=(
                        f"DEMO manifesto: improve primary health care, rural roads and youth skills in {lga_name}."
                    ),
                    status="active",
                )
            )
    db.session.flush()
    return election


def generate_password() -> str:
    return f"Demo-{secrets.token_urlsafe(9)}7"


def wipe_all_data() -> None:
    """Delete every row (used by the destructive local reset command)."""
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
