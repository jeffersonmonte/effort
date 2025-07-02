from fastapi import APIRouter, Depends, HTTPException, status, Request # Added Request
from fastapi.responses import RedirectResponse # Added RedirectResponse
from uuid import UUID
from typing import List

from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud, schemas, models
from app.db import get_async_session
from app.users import current_active_user # Dependency for authenticated user

router = APIRouter()

# Helper function for auth guard: check if current user owns the interview
async def get_interview_from_db_and_check_owner(
    interview_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: models.User = Depends(current_active_user)
) -> models.Interview:
    db_interview = await crud.get_interview_by_id(session=session, interview_id=interview_id)
    if not db_interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    if db_interview.user_id != user.id:
        # Optional: Admins might be allowed to bypass this check
        # if user.role != "admin": # Example admin bypass
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this interview")
    return db_interview


@router.post("/", response_model=schemas.InterviewRead, status_code=status.HTTP_201_CREATED)
async def create_new_interview(
    *,
    session: AsyncSession = Depends(get_async_session),
    current_user: models.User = Depends(current_active_user)
    # No request body needed as per InterviewCreate schema for now
):
    """
    Creates a new interview (status=draft) for the currently authenticated user.
    """
    db_interview = await crud.create_interview(session=session, user=current_user)
    # Need to fetch relationships for the response model if not automatically handled
    # by schema access after session commit.
    # Let's explicitly fetch the full interview data for the response.
    # The InterviewRead schema expects answer_blocks and bpmn_diagram.
    # A fresh get_interview_by_id will ensure these are available if lazy loaded.
    # However, create_interview already returns the db_interview object.
    # Pydantic's from_attributes should handle lazy loading them.
    return db_interview


@router.get("/", response_model=List[schemas.InterviewRead])
async def get_my_interviews(
    *,
    session: AsyncSession = Depends(get_async_session),
    current_user: models.User = Depends(current_active_user)
):
    """
    Returns all interviews owned by the currently authenticated user.
    """
    interviews = await crud.get_interviews_by_user_id(session=session, user_id=current_user.id)
    return interviews


@router.get("/{interview_id}", response_model=schemas.InterviewRead, name="get_specific_interview")
async def get_specific_interview(
    *,
    # interview_id: UUID, # This would be path param, but handled by dependency
    # session: AsyncSession = Depends(get_async_session),
    # current_user: models.User = Depends(current_active_user),
    db_interview: models.Interview = Depends(get_interview_from_db_and_check_owner) # Handles fetch & auth
):
    """
    Returns a specific interview by ID, including its answers and BPMN diagram (if any).
    Only accessible by the interview owner.
    """
    # db_interview = await crud.get_interview_by_id(session=session, interview_id=interview_id)
    # if not db_interview:
    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    # if db_interview.user_id != current_user.id:
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return db_interview


@router.put("/{interview_id}/answers", response_model=schemas.AnswerBlockRead)
async def upsert_interview_answers(
    *,
    # interview_id: UUID, # Handled by dependency
    answers_update: schemas.InterviewAnswersUpdate,
    # session: AsyncSession = Depends(get_async_session),
    # current_user: models.User = Depends(current_active_user),
    db_interview: models.Interview = Depends(get_interview_from_db_and_check_owner) # Handles fetch & auth
):
    """
    Upserts answers for a given phase of an interview.
    Only accessible by the interview owner.
    Interview status must be 'draft'.
    """
    if db_interview.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update answers for an interview that is not in 'draft' status."
        )

    # Need to pass the db_interview object to crud.upsert_answer_block
    # The crud function expects `interview: models.Interview`
    session = await db_interview.get_session() # Get session from the model instance if needed by CRUD
                                            # Or, better, pass session from Depends(get_async_session)
                                            # The db_interview from dependency already has session context.
                                            # Let's ensure crud takes session explicitly.
                                            # My crud.upsert_answer_block expects session.
                                            # The dependency get_interview_from_db_and_check_owner uses a session.
                                            # We need to ensure the same session is used or pass it.
                                            # For now, let's re-fetch session for clarity.

    # Re-fetch session to pass to CRUD, or modify dependency to return session too.
    # Simpler: just depend on get_async_session here as well.
    # The dependency `get_interview_from_db_and_check_owner` already uses a session.
    # It's generally fine to have multiple `Depends(get_async_session)` if they resolve to the same session instance
    # per request, which FastAPI does for generator dependencies.

    # Let's modify get_interview_from_db_and_check_owner to also yield the session,
    # or just add session as a separate dependency here. Adding as separate is cleaner.

    active_session: AsyncSession = Depends(get_async_session) # Get a new session dependency
    # The crud.upsert_answer_block expects the interview object, not just id
    # And it needs the session.
    # The db_interview from dependency is already loaded.

    # We need to ensure the session used by the dependency is the same used here if we pass db_interview.
    # It is, because FastAPI reuses the same dependency instance per request.
    # So, the session used to load db_interview is available implicitly.
    # However, crud functions explicitly ask for a session.
    # So, let's pass the session that `get_interview_from_db_and_check_owner` used.
    # This requires `get_interview_from_db_and_check_owner` to provide it, or we pass a new one.

    # Let's make the CRUD function take the `db_interview` object and the `answers_update`
    # and the session can be obtained from the `db_interview` if it's still attached,
    # or passed explicitly. Explicit is better.
    # The session from `Depends(get_async_session)` here will be the same one.

    # The crud.upsert_answer_block expects `interview: Interview` not `interview_id`.
    # So, pass `db_interview` to it.

    # The session used to load `db_interview` in the dependency is closed after the dependency yields.
    # So we MUST use a new session here for the CRUD operation.
    session_for_upsert: AsyncSession = Depends(get_async_session) # This is the correct way

    answer_block = await crud.upsert_answer_block(
        session=session_for_upsert,
        interview=db_interview, # Pass the fetched and authorized interview
        answer_data=answers_update
    )
    return answer_block


@router.post("/{interview_id}/submit", response_model=schemas.InterviewRead)
async def submit_interview_for_bpmn_generation(
    *,
    request: Request, # Added Request for url_for
    db_interview: models.Interview = Depends(get_interview_from_db_and_check_owner), # Handles fetch & auth
    session: AsyncSession = Depends(get_async_session) # Explicit session for this operation
):
    """
    Marks an interview as 'submitted' and triggers BPMN generation.
    Only accessible by the interview owner.
    Interview status must be 'draft'.
    """
    if db_interview.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview must be in 'draft' status to be submitted."
        )

    session_for_submit: AsyncSession = Depends(get_async_session)

    # 1. Update interview status to "submitted"
    updated_interview = await crud.update_interview_status(
        session=session_for_submit,
        interview=db_interview,
        status="submitted"
    )

    # 2. Trigger BPMN generation (this will be an async task or a direct call)
    # For now, let's assume a direct call to a service function.
    # This service function will use its own session if it needs to save the BPMN diagram.
    from app.services import bpmn_service # Import the service
    try:
        # The service function needs the same session if it's part of the same transaction,
        # or it can manage its own if it's a truly separate unit of work.
        # crud.create_or_update_bpmn_diagram in bpmn_service needs a session.
        # Pass session_for_submit which is the current active session for this request.
        await bpmn_service.generate_and_save_bpmn_for_interview(
            session=session_for_submit, # Use the same session
            interview=updated_interview
        )
        print(f"INFO: BPMN generation process completed for interview {updated_interview.id}")
    except bpmn_service.BPMNGenerationError as e:
        print(f"ERROR: BPMN generation failed for interview {updated_interview.id}: {e}")
        # Optionally, you might want to roll back the status change or set a specific error status.
        # For now, the interview remains "submitted", but BPMN generation failed.
        # The redirect will still happen. Client can check for diagram later or see an error message.
        # Consider adding a message to the user via flash messages if using full page reloads,
        # or specific error handling if HTMX targets an error display area.
    except Exception as e:
        print(f"CRITICAL_ERROR: Unexpected error during BPMN generation for interview {updated_interview.id}: {e}")
        # This is a more severe, unexpected error.
        # Might be appropriate to raise an HTTPException here to inform client of server error.
        # For now, log and proceed with redirect.
        # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BPMN generation failed unexpectedly.")

    # Return the updated interview, which now has status "submitted"
    # The BPMN diagram might not be available immediately if generation is async.
    # The response model InterviewRead will show current state.

    # Instead of returning JSON, redirect to the interview's detail page.
    # The route for get_specific_interview is named 'get_specific_interview' by FastAPI.
    # (or it will be if I add a name="" parameter to its decorator, otherwise it's based on func name)
    # Let's assume the default name works or add a name to get_specific_interview route.
    # For robustness, explicitly naming routes used in url_for is good.
    # I will add `name="get_specific_interview_route"` to the get_specific_interview endpoint.

    # For now, construct URL manually or assume default naming works.
    # The route is GET /{interview_id} under this router.
    # The router is prefixed with /interviews in main.py.
    # So, path is /interviews/{interview_id}

    # The updated_interview object has the id.
    redirect_url = request.url_for("get_specific_interview", interview_id=updated_interview.id)
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{interview_id}/bpmn", response_model=schemas.BpmnDiagramRead)
async def get_interview_bpmn_diagram(
    *,
    # interview_id: UUID, # Handled by dependency
    # session: AsyncSession = Depends(get_async_session),
    # current_user: models.User = Depends(current_active_user),
    db_interview: models.Interview = Depends(get_interview_from_db_and_check_owner) # Handles fetch & auth
):
    """
    Returns the generated BPMN diagram (XML + SVG) for a submitted interview.
    Only accessible by the interview owner.
    """
    if db_interview.status != "submitted" and db_interview.status != "completed": # Or whatever status means BPMN is generated
        # Or, just check if diagram exists
        pass # Allow fetching even if draft, if diagram exists somehow

    session_for_fetch: AsyncSession = Depends(get_async_session)
    diagram = await crud.get_bpmn_diagram_by_interview_id(session=session_for_fetch, interview_id=db_interview.id)

    if not diagram:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BPMN diagram not found for this interview. It might not have been generated yet or the interview is not submitted."
        )
    return diagram

# Note on session management in dependencies:
# The `get_interview_from_db_and_check_owner` dependency uses `Depends(get_async_session)`.
# When this dependency is used in an endpoint, that session is active while the dependency runs.
# If the endpoint itself *also* `Depends(get_async_session)` for other CRUD calls, FastAPI
# ensures that the same session instance is provided for the scope of that request if the
# dependency is a generator (like `get_async_session` is).
# So, `session_for_upsert`, `session_for_submit`, `session_for_fetch` will correctly receive
# a valid session for their operations.
# The `db_interview` object obtained from `get_interview_from_db_and_check_owner` is loaded
# using a session that is closed after `get_interview_from_db_and_check_owner` yields.
# Therefore, any *new* operations on `db_interview` or its relationships in the endpoint
# *must* use a new session obtained via `Depends(get_async_session)` within the endpoint's scope.
# This is why I'm explicitly getting new sessions for subsequent CRUD calls.
# The `db_interview` object itself is just data after its original session is closed.
# To perform further database operations (like saving changes to `db_interview` or loading more relationships),
# it would need to be merged into the new session: `new_session.add(db_interview)` before commit,
# or re-fetched. My CRUD functions handle re-fetching or operate on IDs/data.
# The `update_interview_status` and `upsert_answer_block` take the `db_interview` instance,
# add it to *their* session, and commit. This is a common pattern.
# `crud.update_interview_status(session=session_for_submit, interview=db_interview, ...)`
# This adds `db_interview` to `session_for_submit`. This is fine.
# The `interview` object passed to `upsert_answer_block` and `create_or_update_bpmn_diagram`
# in `app/crud.py` is used for its `id` and to update its `updated_at`. This is also fine.
