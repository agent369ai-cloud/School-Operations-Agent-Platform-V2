"""Optional dev-only seeding script. The real onboarding flow is the
/api/v1/auth/register-school endpoint — this script is for demo speed only.

Usage:  python seed.py            # idempotent; safe to re-run
"""
from app.auth.security import hash_password
from app.database import SessionLocal, init_db
from app.models import (
    ClassRoom, School, StudentEnrollment, TeacherClassroom, User,
)


DEMO_PASSWORD = "demo-password-1234"  # documented in README; not a real secret


def seed_demo_data():
    print("Initialising tables…")
    init_db()
    db = SessionLocal()
    try:
        # --- Lincoln High ---
        lincoln = db.query(School).filter(School.name == "Lincoln High").first()
        if not lincoln:
            lincoln = School(name="Lincoln High")
            db.add(lincoln); db.flush()
            for cname in ("Grade 7-A", "Grade 8-B", "Grade 8-C"):
                db.add(ClassRoom(school_id=lincoln.id, name=cname))
            admin = User(school_id=lincoln.id, email="admin@lincolnhigh.edu",
                         name="Principal Reynolds", role="ADMIN",
                         password_hash=hash_password(DEMO_PASSWORD))
            db.add(admin)
            db.flush()
            print(f"  Lincoln High seeded. Admin: admin@lincolnhigh.edu / {DEMO_PASSWORD}")

        # --- Oxford Academy (for cross-school auth tests) ---
        oxford = db.query(School).filter(School.name == "Oxford Academy").first()
        if not oxford:
            oxford = School(name="Oxford Academy")
            db.add(oxford); db.flush()
            for cname in ("Oxford Grade 7-A", "Oxford Grade 8-B"):
                db.add(ClassRoom(school_id=oxford.id, name=cname))
            oxford_admin = User(school_id=oxford.id, email="admin@oxford.edu",
                                name="Principal Higgins", role="ADMIN",
                                password_hash=hash_password(DEMO_PASSWORD))
            db.add(oxford_admin)
            print(f"  Oxford Academy seeded. Admin: admin@oxford.edu / {DEMO_PASSWORD}")

        db.commit()
        print("Done.")
    except Exception as e:
        db.rollback()
        print(f"Seed error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
