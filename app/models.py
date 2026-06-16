"""SQLAlchemy domain model.

Every resource carries `school_id` (directly or transitively) so the auth
layer can enforce a single rule: actor.school_id must match resource.school_id.
"""
import datetime
import uuid
from sqlalchemy import (
    Column, String, Boolean, ForeignKey, DateTime, JSON, Integer, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


# ---------- Core tenants ----------

class School(Base):
    __tablename__ = "schools"
    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=_now)


class ClassRoom(Base):
    __tablename__ = "classrooms"
    id = Column(String, primary_key=True, default=_uuid)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)  # e.g. "Grade 7-A"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_class_per_school"),)


class User(Base):
    """Admin / Teacher / Student. Guardian lives in its own table because
    a guardian may link to multiple children."""
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=_uuid)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, unique=True, nullable=True, index=True)
    role = Column(String, nullable=False)  # ADMIN | TEACHER | STUDENT
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # null for students/teachers who haven't accepted invite
    created_at = Column(DateTime, default=_now)


class TeacherClassroom(Base):
    """Many-to-many: a teacher can teach multiple classes; a class has multiple teachers."""
    __tablename__ = "teacher_classrooms"
    teacher_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    classroom_id = Column(String, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True)


class StudentEnrollment(Base):
    """Which classroom a student belongs to."""
    __tablename__ = "student_enrollments"
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    classroom_id = Column(String, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True)


# ---------- Guardians ----------

class Guardian(Base):
    __tablename__ = "guardians"
    id = Column(String, primary_key=True, default=_uuid)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    opted_in = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)


class GuardianStudentLink(Base):
    __tablename__ = "guardian_student_links"
    guardian_id = Column(String, ForeignKey("guardians.id", ondelete="CASCADE"), primary_key=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


# ---------- Assignments / Submissions / Feedback ----------

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(String, primary_key=True, default=_uuid)
    classroom_id = Column(String, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    title = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    instructions = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    # DRAFT -> PENDING_APPROVAL -> ACTIVE -> CLOSED/CANCELLED
    status = Column(String, default="DRAFT", nullable=False)
    source_document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime, default=_now)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(String, primary_key=True, default=_uuid)
    assignment_id = Column(String, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # NOT_STARTED -> IN_PROGRESS -> BLOCKED -> SUBMITTED -> FEEDBACK_GIVEN
    #   -> REVISION_REQUESTED -> SUBMITTED -> COMPLETED
    state = Column(String, default="NOT_STARTED", nullable=False)
    content = Column(Text, nullable=True)
    file_path = Column(String, nullable=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_submission_per_student"),)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(String, primary_key=True, default=_uuid)
    submission_id = Column(String, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(String, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    decision = Column(String, nullable=False)  # REVISION_REQUESTED | COMPLETED
    created_at = Column(DateTime, default=_now)


# ---------- Documents ----------

class Document(Base):
    """A document uploaded by an admin/teacher. Stores the original bytes path,
    the parsed JSON, and the approval decision."""
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=_uuid)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    doc_type = Column(String, nullable=False)  # ROSTER | BRIEF | POLICY | SUBMISSION
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=True)
    parsed_json = Column(JSON, nullable=True)
    is_ambiguous = Column(Boolean, default=False)
    approval_state = Column(String, default="PENDING")  # PENDING | APPROVED | REJECTED
    created_at = Column(DateTime, default=_now)


# ---------- Invitations ----------

class Invitation(Base):
    """Scoped, short-lived, single-use invitation token."""
    __tablename__ = "invitations"
    token = Column(String, primary_key=True)
    school_id = Column(String, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    classroom_id = Column(String, ForeignKey("classrooms.id"), nullable=True)
    role = Column(String, nullable=False)  # TEACHER | STUDENT | GUARDIAN
    invitee_email = Column(String, nullable=True)
    invitee_name = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_now)


# ---------- Chat identities (for linking Telegram users to web accounts) ----------

class ChatIdentity(Base):
    __tablename__ = "chat_identities"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String, nullable=False)  # telegram | whatsapp
    channel_user_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=_now)
    __table_args__ = (UniqueConstraint("channel", "channel_user_id", name="uq_chat_identity"),)


# ---------- Idempotency: every inbound chat message is recorded ----------

class InboundChatMessage(Base):
    """De-dup key for webhook retries. Unique on (channel, message_id)."""
    __tablename__ = "inbound_chat_messages"
    id = Column(String, primary_key=True, default=_uuid)
    channel = Column(String, nullable=False)
    message_id = Column(String, nullable=False)
    sender_id = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    processed_at = Column(DateTime, default=_now)
    __table_args__ = (UniqueConstraint("channel", "message_id", name="uq_inbound_msg"),)


# ---------- Audit log ----------

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String, primary_key=True, default=_uuid)
    correlation_id = Column(String, index=True, nullable=False)
    actor_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_now, index=True)
