"""Pydantic schemas for request/response validation."""
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr


# ---------- Auth ----------

class SchoolRegisterIn(BaseModel):
    school_name: str
    admin_name: str
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    school_id: str
    user_id: str


# ---------- Invitations ----------

class InvitationCreateIn(BaseModel):
    role: str = Field(pattern="^(TEACHER|STUDENT|GUARDIAN)$")
    invitee_name: str
    invitee_email: Optional[EmailStr] = None
    classroom_id: Optional[str] = None
    expires_hours: int = 168  # 7 days


class InvitationAcceptIn(BaseModel):
    password: str = Field(min_length=8)


# ---------- Parser ----------

class ParsedAssignment(BaseModel):
    title: str = Field(description="Extracted assignment title")
    subject: str = Field(description="Subject like Math, Science")
    instructions: str = Field(description="Step-by-step instructions for the student")
    due_date: Optional[str] = Field(None, description="ISO due date if present")
    is_ambiguous: bool = Field(description="True if a critical field is missing")
    clarification_question: Optional[str] = Field(
        None, description="Explicit follow-up question if ambiguous"
    )


class RosterAnomaly(BaseModel):
    row: int
    field: str
    issue: str


# ---------- Chat / Intent ----------

class ChatInput(BaseModel):
    """Used by the mock chat router for demo without a real channel."""
    student_id: str
    student_name: str
    message: str
    message_id: Optional[str] = None  # caller may supply for idempotency tests


# ---------- Submissions ----------

class SubmissionCreateIn(BaseModel):
    assignment_id: str
    content: Optional[str] = None  # text submission


class FeedbackIn(BaseModel):
    text: str
    decision: str = Field(pattern="^(REVISION_REQUESTED|COMPLETED)$")


# ---------- Assignment approval ----------

class AssignmentApprovalIn(BaseModel):
    due_date: Optional[str] = None
    title: Optional[str] = None
    instructions: Optional[str] = None
    approve: bool = True
