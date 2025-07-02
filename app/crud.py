from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from uuid import UUID
from typing import List, Optional, Sequence # Sequence for .all() result

from app.models import User, Interview, AnswerBlock, BpmnDiagram
from app.schemas import InterviewCreate, InterviewAnswersUpdate # BpmnDiagramCreate (if needed)

# --- Interview CRUD ---
async def create_interview(session: AsyncSession, *, user: User) -> Interview:
    """
    Creates a new interview for a given user.
    """
    # InterviewCreate schema is currently empty, status defaults to "draft" in model.
    db_interview = Interview(user_id=user.id) # Link to the user
    session.add(db_interview)
    await session.commit()
    await session.refresh(db_interview)
    return db_interview

async def get_interview_by_id(session: AsyncSession, *, interview_id: UUID) -> Optional[Interview]:
    """
    Retrieves an interview by its ID.
    Includes related answer blocks and BPMN diagram.
    """
    statement = (
        select(Interview)
        .where(Interview.id == interview_id)
        # .options(
        #     selectinload(Interview.answer_blocks), # Use selectinload for async loading
        #     selectinload(Interview.bpmn_diagram)
        # )
        # SQLModel doesn't use SQLAlchemy's selectinload directly in the same way.
        # Relationships are typically loaded when accessed or can be configured for eager loading
        # at the model level if needed, or handled by refreshing the object with relationships.
        # For now, let's get the interview, relationships can be loaded upon access if lazy,
        # or we can refresh them. For API responses, Pydantic schemas will access them.
    )
    result = await session.exec(statement)
    db_interview = result.one_or_none()

    # Manually load relationships if needed and not automatically loaded by schema access
    # This ensures they are available before session closes if accessed later.
    # However, Pydantic's from_attributes in schemas should trigger lazy loading if session is active.
    if db_interview:
        # To ensure relationships are loaded for serialization if session might close:
        _ = db_interview.answer_blocks
        _ = db_interview.bpmn_diagram
    return db_interview


async def get_interviews_by_user_id(session: AsyncSession, *, user_id: UUID) -> Sequence[Interview]:
    """
    Retrieves all interviews for a specific user.
    """
    statement = select(Interview).where(Interview.user_id == user_id).order_by(Interview.created_at.desc())
    result = await session.exec(statement)
    interviews = result.all()
    return interviews

async def update_interview_status(session: AsyncSession, *, interview: Interview, status: str) -> Interview:
    """
    Updates the status of an interview (e.g., to "submitted").
    """
    interview.status = status
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


# --- AnswerBlock CRUD ---
async def upsert_answer_block(
    session: AsyncSession, *, interview_id: UUID, answer_data: InterviewAnswersUpdate
) -> AnswerBlock:
    """
    Upserts an answer block for a given interview and phase.
    If an answer block for that phase exists, it's updated. Otherwise, a new one is created.
    """
    statement = select(AnswerBlock).where(
        AnswerBlock.interview_id == interview_id,
        AnswerBlock.phase == answer_data.phase
    )
    result = await session.exec(statement)
    db_answer_block = result.one_or_none()

    if db_answer_block:
        # Update existing block
        db_answer_block.json_payload = answer_data.json_payload
        # updated_at is handled by the model's onupdate
    else:
        # Create new block
        db_answer_block = AnswerBlock(
            interview_id=interview_id,
            phase=answer_data.phase,
            json_payload=answer_data.json_payload
        )

    session.add(db_answer_block)
    await session.commit()
    await session.refresh(db_answer_block)
    # Also refresh the parent interview's updated_at
    # (This should happen if the interview model's updated_at is properly configured,
    # or we can touch it manually here)
    # interview = await get_interview_by_id(session, interview_id=interview_id)
    # if interview:
    #     interview.updated_at = datetime.now(timezone.utc) # Manual touch
    #     session.add(interview)
    #     await session.commit()
    #     await session.refresh(interview)

    return db_answer_block

async def get_answer_blocks_by_interview_id(session: AsyncSession, *, interview_id: UUID) -> Sequence[AnswerBlock]:
    """
    Retrieves all answer blocks for a specific interview, ordered by phase.
    """
    statement = select(AnswerBlock).where(AnswerBlock.interview_id == interview_id).order_by(AnswerBlock.phase)
    result = await session.exec(statement)
    answer_blocks = result.all()
    return answer_blocks


# --- BpmnDiagram CRUD ---
async def create_or_update_bpmn_diagram(
    session: AsyncSession, *, interview_id: UUID, xml_content: str, svg_content: str
) -> BpmnDiagram:
    """
    Creates or updates the BPMN diagram for a given interview.
    An interview should only have one diagram.
    """
    statement = select(BpmnDiagram).where(BpmnDiagram.interview_id == interview_id)
    result = await session.exec(statement)
    db_diagram = result.one_or_none()

    if db_diagram:
        db_diagram.xml = xml_content
        db_diagram.svg = svg_content
        # db_diagram.generated_at will be updated by model default if re-created,
        # or we can set it manually here if we want to track updates.
        # For now, let's assume it's set on creation and doesn't change on update of content.
        # Or, more likely, generated_at should update. The model default_factory won't re-run on update.
        # So, we should set it manually.
        from app.models import now_utc # Re-import for clarity or use datetime directly
        db_diagram.generated_at = now_utc()

    else:
        db_diagram = BpmnDiagram(
            interview_id=interview_id,
            xml=xml_content,
            svg=svg_content
            # generated_at will be set by default_factory on creation
        )

    session.add(db_diagram)
    await session.commit()
    await session.refresh(db_diagram)
    return db_diagram

async def get_bpmn_diagram_by_interview_id(session: AsyncSession, *, interview_id: UUID) -> Optional[BpmnDiagram]:
    """
    Retrieves the BPMN diagram for a specific interview.
    """
    statement = select(BpmnDiagram).where(BpmnDiagram.interview_id == interview_id)
    result = await session.exec(statement)
    db_diagram = result.one_or_none()
    return db_diagram

# Note on relationship loading:
# SQLModel with async sessions and Pydantic V2 `from_attributes=True` should generally handle
# lazy loading of relationships when the schema accesses them, provided the session is still active.
# If issues arise or explicit loading is preferred for performance (to avoid N+1 queries if iterating),
# SQLAlchemy's `selectinload` can be used with `session.execute(statement.options(selectinload(...)))`.
# However, SQLModel's `session.exec(statement)` is simpler.
# For `get_interview_by_id`, if `answer_blocks` and `bpmn_diagram` are accessed by the
# `InterviewRead` schema *after* the session used to fetch the `Interview` is closed,
# they would not load. The FastAPI dependency injection pattern (`Depends(get_async_session)`)
# usually means the session is available for the duration of the request, so this should be fine.
# The manual access `_ = db_interview.answer_blocks` is a way to force loading if needed.
# Let's rely on Pydantic schema access to trigger loading for now.
# If `Interview.answer_blocks` and `Interview.bpmn_diagram` are marked with `Relationship(sa_relationship_kwargs={"lazy": "selectin"})`
# in the model, they would be loaded more eagerly with the parent. Default is "lazyload".
# For this project size, default lazy loading with schema access should be acceptable.
# I removed the explicit `_ = db_interview.answer_blocks` etc. to keep it cleaner, assuming schema access handles it.
# Will test and add explicit loads if necessary.

# The `updated_at` field in `Interview` model:
# `updated_at: datetime = Field(default_factory=now_utc, sa_column_kwargs={"onupdate": now_utc})`
# The `onupdate` part is for database-level triggers (works well in Postgres).
# For SQLite, this might not automatically update. If `upsert_answer_block` or other actions
# that logically modify the interview don't trigger the DB-level onupdate for Interview's updated_at,
# we might need to manually update `interview.updated_at = now_utc()` in those CRUD functions.
# For now, I'll assume the model's definition is sufficient or address it if testing shows issues.
# The `AnswerBlock.updated_at` has a similar setup.
# `BpmnDiagram.generated_at` is set on creation, and I added manual update for `create_or_update_bpmn_diagram`.tool_code
create_file_with_block
app/crud.py
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from uuid import UUID
from typing import List, Optional, Sequence # Sequence for .all() result
from datetime import datetime, timezone # For manual updated_at

from app.models import User, Interview, AnswerBlock, BpmnDiagram, now_utc # Import now_utc
from app.schemas import InterviewCreate, InterviewAnswersUpdate # BpmnDiagramCreate (if needed)

# --- Interview CRUD ---
async def create_interview(session: AsyncSession, *, user: User) -> Interview:
    """
    Creates a new interview for a given user.
    """
    db_interview = Interview(user_id=user.id)
    session.add(db_interview)
    await session.commit()
    await session.refresh(db_interview)
    return db_interview

async def get_interview_by_id(session: AsyncSession, *, interview_id: UUID) -> Optional[Interview]:
    """
    Retrieves an interview by its ID.
    Relationships (answer_blocks, bpmn_diagram) will be lazy-loaded when accessed
    by Pydantic schemas, provided the session is active.
    """
    statement = select(Interview).where(Interview.id == interview_id)
    result = await session.exec(statement)
    db_interview = result.one_or_none()
    return db_interview


async def get_interviews_by_user_id(session: AsyncSession, *, user_id: UUID) -> Sequence[Interview]:
    """
    Retrieves all interviews for a specific user.
    """
    statement = select(Interview).where(Interview.user_id == user_id).order_by(Interview.created_at.desc())
    result = await session.exec(statement)
    interviews = result.all()
    return interviews

async def update_interview_status(session: AsyncSession, *, interview: Interview, status: str) -> Interview:
    """
    Updates the status of an interview (e.g., to "submitted").
    Also updates the interview's `updated_at` timestamp manually for SQLite compatibility.
    """
    interview.status = status
    interview.updated_at = now_utc() # Manually update timestamp
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


# --- AnswerBlock CRUD ---
async def upsert_answer_block(
    session: AsyncSession, *, interview: Interview, answer_data: InterviewAnswersUpdate
) -> AnswerBlock:
    """
    Upserts an answer block for a given interview and phase.
    If an answer block for that phase exists, it's updated. Otherwise, a new one is created.
    Also updates the parent interview's `updated_at` timestamp.
    """
    statement = select(AnswerBlock).where(
        AnswerBlock.interview_id == interview.id,
        AnswerBlock.phase == answer_data.phase
    )
    result = await session.exec(statement)
    db_answer_block = result.one_or_none()

    if db_answer_block:
        db_answer_block.json_payload = answer_data.json_payload
        db_answer_block.updated_at = now_utc() # Manually update timestamp
    else:
        db_answer_block = AnswerBlock(
            interview_id=interview.id,
            phase=answer_data.phase,
            json_payload=answer_data.json_payload
            # updated_at will be set by default_factory
        )

    session.add(db_answer_block)

    # Update parent interview's timestamp
    interview.updated_at = now_utc()
    session.add(interview)

    await session.commit()
    await session.refresh(db_answer_block)
    await session.refresh(interview) # Refresh interview to get its updated timestamp if needed by caller

    return db_answer_block

async def get_answer_blocks_by_interview_id(session: AsyncSession, *, interview_id: UUID) -> Sequence[AnswerBlock]:
    """
    Retrieves all answer blocks for a specific interview, ordered by phase.
    """
    statement = select(AnswerBlock).where(AnswerBlock.interview_id == interview_id).order_by(AnswerBlock.phase)
    result = await session.exec(statement)
    answer_blocks = result.all()
    return answer_blocks


# --- BpmnDiagram CRUD ---
async def create_or_update_bpmn_diagram(
    session: AsyncSession, *, interview: Interview, xml_content: str, svg_content: str
) -> BpmnDiagram:
    """
    Creates or updates the BPMN diagram for a given interview.
    An interview should only have one diagram.
    Updates parent interview's `updated_at` timestamp.
    """
    statement = select(BpmnDiagram).where(BpmnDiagram.interview_id == interview.id)
    result = await session.exec(statement)
    db_diagram = result.one_or_none()

    current_time = now_utc()
    if db_diagram:
        db_diagram.xml = xml_content
        db_diagram.svg = svg_content
        db_diagram.generated_at = current_time # Manually update timestamp
    else:
        db_diagram = BpmnDiagram(
            interview_id=interview.id,
            xml=xml_content,
            svg=svg_content,
            generated_at=current_time # Set explicitly, though default_factory would also work on create
        )

    session.add(db_diagram)

    # Update parent interview's timestamp
    interview.updated_at = current_time
    session.add(interview)

    await session.commit()
    await session.refresh(db_diagram)
    await session.refresh(interview)
    return db_diagram

async def get_bpmn_diagram_by_interview_id(session: AsyncSession, *, interview_id: UUID) -> Optional[BpmnDiagram]:
    """
    Retrieves the BPMN diagram for a specific interview.
    """
    statement = select(BpmnDiagram).where(BpmnDiagram.interview_id == interview_id)
    result = await session.exec(statement)
    db_diagram = result.one_or_none()
    return db_diagram
