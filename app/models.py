from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, JSON # Import Column and JSON
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone # Use timezone-aware datetimes
from uuid import uuid4, UUID

# Helper function for timezone-aware UTC now
def now_utc():
    return datetime.now(timezone.utc)

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    email: str = Field(unique=True, index=True, max_length=255) # Added max_length
    hashed_password: Optional[str] = Field(default=None, max_length=1024) # For fastapi-users
    role: str = Field(default="expert", max_length=50) # Added max_length

    is_active: bool = Field(default=True) # For fastapi-users
    is_superuser: bool = Field(default=False) # For fastapi-users
    is_verified: bool = Field(default=False) # For fastapi-users

    interviews: List["Interview"] = Relationship(back_populates="user")

class Interview(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    status: str = Field(default="draft", index=True, max_length=50) # Added max_length
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc, sa_column_kwargs={"onupdate": now_utc})

    user: User = Relationship(back_populates="interviews")
    answer_blocks: List["AnswerBlock"] = Relationship(back_populates="interview") # Renamed from blocks for clarity
    bpmn_diagram: Optional["BpmnDiagram"] = Relationship(back_populates="interview") # Renamed from bpmn for clarity

class AnswerBlock(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    interview_id: UUID = Field(foreign_key="interview.id", index=True)
    phase: int = Field(index=True)
    json_payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON)) # Explicitly use JSON type
    updated_at: datetime = Field(default_factory=now_utc, sa_column_kwargs={"onupdate": now_utc})

    interview: Interview = Relationship(back_populates="answer_blocks")

class BpmnDiagram(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    # Making interview_id unique to ensure one diagram per interview
    interview_id: UUID = Field(foreign_key="interview.id", unique=True, index=True)
    xml: str # Can be large, consider TEXT type if DB supports it explicitly via SQLModel/SQLAlchemy
    svg: str # Can be large
    generated_at: datetime = Field(default_factory=now_utc)

    interview: Interview = Relationship(back_populates="bpmn_diagram")

# Note: For fastapi-users, the User model needs specific fields:
# is_active: bool, is_superuser: bool, is_verified: bool. I've added them.
# The `hashed_password` field should also be Optional[str] as per fastapi-users convention.
# `email` needs to be unique.
# Max lengths are good practice for string fields.
# Using timezone-aware datetimes (UTC) is crucial.
# `sa_column_kwargs={"onupdate": now_utc}` for `updated_at` fields for automatic update on DB level if supported.
# For SQLite, onupdate might behave differently or need triggers; for Postgres, it's fine.
# SQLModel should handle dict to JSON conversion.
# Renamed 'blocks' to 'answer_blocks' and 'bpmn' to 'bpmn_diagram' in Interview model for better clarity.
# Added index=True to foreign keys and other frequently queried fields for performance.
