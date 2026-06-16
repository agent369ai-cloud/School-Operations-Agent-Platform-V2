"""Authorization tests — every protected resource must enforce school_id scope."""


def _token(client, email, password="longenoughpassword"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def _create_class(client, token, name):
    r = client.post("/api/v1/classrooms", json={"name": name},
                    headers={"Authorization": f"Bearer {token}"})
    return r.json()["id"]


def test_admin_can_create_classroom_in_own_school(client, school_a):
    token = _token(client, "admin@alpha.edu")
    r = client.post("/api/v1/classrooms", json={"name": "G7"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert r.json()["name"] == "G7"


def test_admin_cannot_read_other_schools_classroom(client, school_a, school_b):
    token_a = _token(client, "admin@alpha.edu")
    token_b = _token(client, "admin@beta.edu")

    # Beta admin creates a classroom
    class_b = _create_class(client, token_b, "Beta Class")

    # Alpha admin tries to read it
    r = client.get(f"/api/v1/classrooms/{class_b}",
                   headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 403


def test_cross_school_access_writes_audit_event(client, school_a, school_b, db_session):
    """The ACCESS_DENIED audit event is the only privacy-safe forensic trail."""
    token_a = _token(client, "admin@alpha.edu")
    token_b = _token(client, "admin@beta.edu")
    class_b = _create_class(client, token_b, "Beta Class")

    client.get(f"/api/v1/classrooms/{class_b}",
               headers={"Authorization": f"Bearer {token_a}"})

    # Walk the audit log
    r = client.get("/api/v1/mock/audit-timeline")
    events = r.json()["events"]
    denied = [e for e in events if e["event_type"] == "ACCESS_DENIED"]
    assert len(denied) >= 1
    assert denied[0]["payload"]["reason"] == "cross_school_attempt"


def test_student_role_cannot_create_classroom(client, school_a):
    """Role gating: only ADMIN can create classrooms."""
    # First create an invitation as admin
    token_admin = _token(client, "admin@alpha.edu")
    inv = client.post("/api/v1/invitations", json={
        "role": "STUDENT", "invitee_name": "Bob", "invitee_email": "bob@alpha.edu",
    }, headers={"Authorization": f"Bearer {token_admin}"}).json()
    accept = client.post(f"/api/v1/invitations/{inv['token']}/accept",
                         json={"password": "studentpassword"}).json()
    student_token = accept["access_token"]

    r = client.post("/api/v1/classrooms", json={"name": "Should fail"},
                    headers={"Authorization": f"Bearer {student_token}"})
    assert r.status_code == 403
