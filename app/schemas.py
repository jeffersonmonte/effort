from fastapi_users import schemas as fu_schemas
from pydantic import BaseModel, EmailStr, Field as PydanticField # Alias Pydantic's Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

# SQLModel models are often used directly for responses if they match the desired shape.
# Pydantic schemas are useful for request bodies, complex responses, or when shapes differ.

class UserRead(fu_schemas.BaseUser[UUID]):
    # Inherits id, email, is_active, is_superuser, is_verified from BaseUser
    # Add any custom fields you want to expose when reading a user
    role: str

class UserCreate(fu_schemas.BaseUserCreate):
    # Inherits email, password from BaseUserCreate
    # Add any custom fields for user creation
    role: Optional[str] = "expert" # Default role on creation

class UserUpdate(fu_schemas.BaseUserUpdate):
    # Inherits password, is_active, is_superuser, is_verified (all optional)
    # Add any custom fields for user update
    role: Optional[str] = None


# Schemas for Interview data
class AnswerBlockBase(BaseModel):
    phase: int
    json_payload: Dict[str, Any]

class AnswerBlockCreate(AnswerBlockBase):
    pass

class AnswerBlockRead(AnswerBlockBase):
    id: UUID
    updated_at: datetime

    class Config:
        orm_mode = True # Pydantic V1 style, for Pydantic V2 use from_attributes=True

class BpmnDiagramBase(BaseModel):
    xml: str
    svg: str

class BpmnDiagramRead(BpmnDiagramBase):
    id: UUID
    generated_at: datetime
    interview_id: UUID # Added for context

    class Config:
        orm_mode = True


class InterviewBase(BaseModel):
    # Fields that are common for creation and reading, if any
    # For now, let specific schemas define their fields
    pass

class InterviewCreate(InterviewBase):
    # user_id will be set from the current authenticated user, not from request body
    pass # No fields needed from client to create an interview initially by an auth user

class InterviewRead(InterviewBase):
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    answer_blocks: List[AnswerBlockRead] = []
    bpmn_diagram: Optional[BpmnDiagramRead] = None

    class Config:
        orm_mode = True

# Schema for submitting answers to a phase
class InterviewAnswersUpdate(BaseModel):
    phase: int
    json_payload: Dict[str, Any]


# It's good practice to separate internal models (SQLModel) from API schemas (Pydantic).
# SQLModel models can sometimes be used directly if they are simple and map 1:1.
# However, for request validation (e.g. UserCreate needing a password not in User model),
# and for controlling what's exposed in responses, separate Pydantic schemas are better.
# `fastapi-users` encourages this pattern with its BaseUser, BaseUserCreate schemas.

# Note on Pydantic V2: orm_mode is now from_attributes=True
# I will update this to use from_attributes=True for Pydantic V2 compatibility.
# For now, I'll leave orm_mode as many projects still use it transitionally,
# but I'll make a note to update if mypy/pydantic complain.
# SQLModel itself is built on Pydantic v2, so from_attributes=True is the way to go.
# I'll update this now.

class AnswerBlockReadUpdated(AnswerBlockBase):
    id: UUID
    updated_at: datetime
    model_config = {"from_attributes": True}


class BpmnDiagramReadUpdated(BpmnDiagramBase):
    id: UUID
    generated_at: datetime
    interview_id: UUID
    model_config = {"from_attributes": True}


class InterviewReadUpdated(InterviewBase):
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    answer_blocks: List[AnswerBlockReadUpdated] = [] # Use updated version
    bpmn_diagram: Optional[BpmnDiagramReadUpdated] = None # Use updated version
    model_config = {"from_attributes": True}

# Re-aliasing for clarity in the rest of the app
AnswerBlockRead = AnswerBlockReadUpdated
BpmnDiagramRead = BpmnDiagramReadUpdated
InterviewRead = InterviewReadUpdated

# For magic link request
class MagicLinkRequest(BaseModel):
    email: EmailStr
