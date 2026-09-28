"""Give the demo accounts North Indian names and predictable passwords.

    DATABASE_URL=... python scripts/rebrand_demo_accounts.py [--dry-run]

Only rows the seed created (`users.is_demo`) are touched. Anything somebody
made by hand is left exactly as it is, including the administrator you sign in
with -- this script must never be the reason a real account changes.

Names are assigned deterministically from the registration number, so running
it twice gives the same person the same name, and a database seeded later
lines up with a record exported earlier.

Passwords follow one rule: the given name in lower case, then 123456
(`aarav123456`). That is eleven characters, clears MIN_PASSWORD_LENGTH, and is
not in the common-password blocklist -- checked here rather than assumed, so
the script fails loudly if the policy tightens.

These are demonstration accounts holding fictional data on a demonstration
deployment. The scheme is deliberately guessable because its purpose is to let
somebody sign in as each role while showing the system. It would be entirely
wrong for real accounts.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_demo_data import _demo_registration_number  # noqa: E402  - one scheme, one place

import app.db.model_registry  # noqa: F401,E402  - registers every table, so

# the User model's foreign keys resolve. Without it SQLAlchemy cannot map the
# departments reference and every query fails.
from app.core.config import get_settings  # noqa: E402
from app.core.security import (  # noqa: E402
    MIN_PASSWORD_LENGTH,
    hash_password,
    is_common_password,
)
from app.modules.users.models import User  # noqa: E402

GIVEN_NAMES: tuple[str, ...] = (
    "Aarav",
    "Aditya",
    "Akash",
    "Amit",
    "Anmol",
    "Ankit",
    "Arjun",
    "Ayush",
    "Chirag",
    "Deepak",
    "Dev",
    "Gagan",
    "Gaurav",
    "Hardik",
    "Harsh",
    "Ishaan",
    "Jatin",
    "Kabir",
    "Karan",
    "Kunal",
    "Lakshya",
    "Madhav",
    "Manish",
    "Mohit",
    "Naveen",
    "Nikhil",
    "Nitin",
    "Parth",
    "Pawan",
    "Pranav",
    "Raghav",
    "Rahul",
    "Rishabh",
    "Rohan",
    "Sahil",
    "Sameer",
    "Sanjay",
    "Shubham",
    "Siddharth",
    "Tarun",
    "Tushar",
    "Varun",
    "Vikram",
    "Vivaan",
    "Yash",
    "Yuvraj",
    "Aanya",
    "Aditi",
    "Anika",
    "Anjali",
    "Ananya",
    "Bhavya",
    "Charu",
    "Deepika",
    "Divya",
    "Diya",
    "Esha",
    "Garima",
    "Gauri",
    "Harleen",
    "Ira",
    "Ishita",
    "Jyoti",
    "Kavya",
    "Khushi",
    "Kiran",
    "Lavanya",
    "Mahima",
    "Manvi",
    "Meera",
    "Naina",
    "Neha",
    "Nidhi",
    "Payal",
    "Pooja",
    "Prisha",
    "Radhika",
    "Ritika",
    "Riya",
    "Saanvi",
    "Sakshi",
    "Shreya",
    "Simran",
    "Sneha",
    "Swati",
    "Tanvi",
    "Trisha",
    "Vaishnavi",
    "Vidhi",
    "Yamini",
)

SURNAMES: tuple[str, ...] = (
    "Sharma",
    "Verma",
    "Gupta",
    "Singh",
    "Mehta",
    "Chopra",
    "Malhotra",
    "Kapoor",
    "Bansal",
    "Agarwal",
    "Jain",
    "Arora",
    "Bhatia",
    "Chauhan",
    "Dhillon",
    "Gill",
    "Grewal",
    "Joshi",
    "Kohli",
    "Khanna",
    "Mittal",
    "Nagpal",
    "Oberoi",
    "Pandey",
    "Rana",
    "Saini",
    "Sethi",
    "Sood",
    "Tandon",
    "Thakur",
    "Tiwari",
    "Trivedi",
    "Vohra",
    "Yadav",
    "Ahuja",
    "Bajaj",
    "Chadha",
    "Dua",
    "Garg",
    "Handa",
    "Jindal",
    "Kaushik",
    "Luthra",
    "Madan",
    "Narang",
    "Rastogi",
    "Sachdeva",
    "Bhardwaj",
    "Goel",
    "Sinha",
)

PASSWORD_SUFFIX = "123456"

#: Names the seed generates. Anything matching is a placeholder worth
#: replacing; anything else was chosen by a person and is left alone.
PLACEHOLDER = re.compile(r"^Demo\s", re.IGNORECASE)

#: The old obviously-fake registration numbers, e.g. DEMOFACULTY07. A demo
#: account still carrying one gets an LPU-shaped number derived from its email
#: by the same function the seed uses, so both routes agree.
OLD_STYLE_NUMBER = re.compile(r"^DEMO[A-Z]", re.IGNORECASE)


def password_for(full_name: str) -> str:
    """The given name in lower case, then 123456.

    A three-letter given name would give a nine-character password, one short
    of MIN_PASSWORD_LENGTH -- "Dev Sharma" is the case in this data. Those
    fall back to the whole name run together (`devsharma123456`) rather than
    being padded with something nobody could guess from the rule.
    """
    parts = [part for part in full_name.split() if part]
    given = parts[0].lower() if parts else "researcher"
    candidate = f"{given}{PASSWORD_SUFFIX}"
    if len(candidate) >= MIN_PASSWORD_LENGTH:
        return candidate
    joined = "".join(parts).lower()
    return f"{joined}{PASSWORD_SUFFIX}"


def name_for(index: int) -> str:
    """A stable name for the nth demo account.

    Striding the surname list by a number coprime with its length means
    consecutive accounts get different surnames rather than fifty Sharmas
    before the first Verma.
    """
    given = GIVEN_NAMES[index % len(GIVEN_NAMES)]
    surname = SURNAMES[(index * 7) % len(SURNAMES)]
    return f"{given} {surname}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would change, write nothing"
    )
    parser.add_argument(
        "--rename-all",
        action="store_true",
        help=(
            "also rename demo accounts that already have a real-looking name. "
            "Off by default: those names were chosen by somebody."
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    factory = sessionmaker(bind=engine)
    changed = 0
    try:
        with factory() as db:
            # Ordered by registration number so the assignment is stable
            # whatever order the rows come back in.
            users = list(
                db.scalars(
                    select(User).where(User.is_demo.is_(True)).order_by(User.registration_number)
                ).all()
            )
            if not users:
                print("No demo accounts found. Nothing to do.")
                return 0

            renamed = 0
            renumbered = 0
            taken = {
                number for number in db.scalars(select(User.registration_number)).all() if number
            }
            for index, user in enumerate(users):
                # A name somebody chose is left alone unless asked otherwise;
                # the password scheme still applies to every demo account, so
                # every demo login follows one rule.
                placeholder = bool(PLACEHOLDER.match(user.full_name or ""))
                full_name = name_for(index) if (placeholder or args.rename_all) else user.full_name
                password = password_for(full_name)
                if len(password) < MIN_PASSWORD_LENGTH or is_common_password(password):
                    print(
                        f"REFUSED: {password!r} would not satisfy the password policy.",
                        file=sys.stderr,
                    )
                    return 1
                # A DEMO-prefixed number becomes an LPU-shaped one. Anything
                # already numeric was assigned deliberately and is kept.
                new_number = user.registration_number
                if OLD_STYLE_NUMBER.match(user.registration_number or "") and user.email:
                    candidate = _demo_registration_number(user.email)
                    if candidate != user.registration_number and candidate not in taken:
                        taken.discard(user.registration_number)
                        taken.add(candidate)
                        new_number = candidate

                if full_name != user.full_name:
                    renamed += 1
                if new_number != user.registration_number:
                    renumbered += 1
                if args.dry_run:
                    arrow = f" -> {full_name!r}" if full_name != user.full_name else " (name kept)"
                    number = (
                        f"{user.registration_number} -> {new_number}"
                        if new_number != user.registration_number
                        else user.registration_number
                    )
                    print(f"  {number:24s} {user.full_name!r}{arrow}")
                else:
                    user.registration_number = new_number
                    user.full_name = full_name
                    user.password_hash = hash_password(password)
                    # A demo account is meant to be signed straight into.
                    user.must_change_password = False
                changed += 1

            if not args.dry_run:
                db.commit()
    finally:
        engine.dispose()

    if args.dry_run:
        print(
            f"\n{changed} demo accounts would be updated "
            f"({renamed} renamed, {renumbered} renumbered). Real accounts are never touched."
        )
    else:
        print(
            f"\n{changed} demo accounts updated "
            f"({renamed} renamed, {renumbered} renumbered). Real accounts were not touched."
        )
        print("Every password is the given name in lower case followed by 123456.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
