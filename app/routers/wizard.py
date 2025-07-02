from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from uuid import UUID
from typing import Dict, Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud, models, schemas
from app.db import get_async_session
from app.users import current_active_user
from app.main import templates # Import templates instance from main.py

# Dependency to get interview and check ownership (similar to the one in interviews.py)
# but adapted for wizard context if needed, or reuse if identical.
# For now, let's define one here for clarity, or we can refactor to a common place.
async def get_wizard_interview_and_check_owner(
    interview_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: models.User = Depends(current_active_user)
) -> models.Interview:
    db_interview = await crud.get_interview_by_id(session=session, interview_id=interview_id)
    if not db_interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found.")
    if db_interview.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this interview.")
    return db_interview

router = APIRouter()

@router.get("/{interview_id}/phase/{phase_number}", response_class=HTMLResponse)
async def get_wizard_phase(
    request: Request,
    interview_id: UUID,
    phase_number: int,
    db_interview: models.Interview = Depends(get_wizard_interview_and_check_owner),
    session: AsyncSession = Depends(get_async_session), # For fetching existing answers
    current_user: models.User = Depends(current_active_user) # To pass to template
):
    """
    Renders a specific phase of the wizard for a given interview.
    """
    if not 1 <= phase_number <= 5:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid phase number.")

    # Fetch existing answers for this phase, if any
    existing_answers_for_phase: Dict[str, Any] = {}
    if db_interview.status == "draft": # Only load drafts for draft interviews
        answer_block_statement = select(models.AnswerBlock).where(
            models.AnswerBlock.interview_id == interview_id,
            models.AnswerBlock.phase == phase_number
        )
        answer_block_result = await session.exec(answer_block_statement)
        db_answer_block = answer_block_result.one_or_none()
        if db_answer_block:
            existing_answers_for_phase = db_answer_block.json_payload

    # Phase-specific logic or data can be prepared here
    # For now, just pass common data.
    context = {
        "request": request,
        "interview": db_interview,
        "phase_number": phase_number,
        "current_user": current_user, # Make user available to template
        "form_data": existing_answers_for_phase, # Pre-fill form if data exists
        "total_phases": 5 # Or get from config
    }

    template_name = f"wizard/phase_{phase_number}.html"
    try:
        return templates.TemplateResponse(template_name, context)
    except Exception as e: # Catch if template doesn't exist
        print(f"Error rendering template {template_name}: {e}") # Log error
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Wizard phase {phase_number} template not found.")


@router.post("/{interview_id}/phase/{phase_number}", response_class=HTMLResponse)
async def handle_wizard_phase_submission(
    request: Request,
    interview_id: UUID,
    phase_number: int,
    db_interview: models.Interview = Depends(get_wizard_interview_and_check_owner),
    session: AsyncSession = Depends(get_async_session),
    current_user: models.User = Depends(current_active_user),
    # Form data will be collected using `request.form()` for dynamic fields
    # or define Pydantic models if fields are fixed per phase.
    # For dynamic questions, `request.form()` is more flexible.
):
    """
    Handles form submission for a wizard phase.
    Saves data via API call (or direct CRUD) and redirects to the next phase or review page.
    """
    if not 1 <= phase_number <= 5:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid phase number.")

    if db_interview.status != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Interview is not in draft status.")

    form_data = await request.form()
    # Convert ImmutableMultiDict to a simple dict for json_payload
    payload: Dict[str, Any] = {key: value for key, value in form_data.items()}

    # Validate payload if necessary (e.g. using Pydantic models per phase)
    # For now, assume direct save.

    # Special handling for Phase 2: Etapas do Processo (list of etapas)
    if phase_number == 2:
        # Fetch existing phase 2 data
        stmt_existing_p2 = select(models.AnswerBlock).where(
            models.AnswerBlock.interview_id == interview_id,
            models.AnswerBlock.phase == 2
        )
        existing_p2_block_result = await session.exec(stmt_existing_p2)
        existing_p2_block = existing_p2_block_result.one_or_none()

        etapas_list = []
        if existing_p2_block and isinstance(existing_p2_block.json_payload.get("etapas"), list):
            etapas_list = existing_p2_block.json_payload["etapas"]

        # Append new etapa (payload contains the new etapa's data)
        # We need to remove any control fields like _action if they were part of the form
        new_etapa_data = {k: v for k, v in payload.items() if not k.startswith('_')}
        etapas_list.append(new_etapa_data)

        # Update the payload for phase 2 to be the list of etapas
        final_payload_for_phase2 = {"etapas": etapas_list}
        answers_update_schema = schemas.InterviewAnswersUpdate(phase=phase_number, json_payload=final_payload_for_phase2)
    else:
        # For other phases, payload is the direct form data
        answers_update_schema = schemas.InterviewAnswersUpdate(phase=phase_number, json_payload=payload)

    try:
        await crud.upsert_answer_block(
            session=session,
            interview=db_interview,
            answer_data=answers_update_schema
        )
    except Exception as e:
        # Handle CRUD error, perhaps re-render form with error messages
        print(f"Error saving answers for phase {phase_number}, interview {interview_id}: {e}")
        # For now, re-raise or return a generic error page/message
        # In a real app, you'd re-render the current phase's form with errors.
        # This requires passing error messages to the template.
        # For HTMX, you could return a partial HTML with errors to swap into the form.
        # Or, if not using HTMX for error handling within the page, a full page reload with errors.
        context = {
            "request": request,
            "interview": db_interview,
            "phase_number": phase_number,
            "current_user": current_user,
            "form_data": payload, # Re-fill form with submitted data
            "error_message": f"Failed to save answers: {e}", # Generic error
            "total_phases": 5
        }
        template_name = f"wizard/phase_{phase_number}.html"
        return templates.TemplateResponse(template_name, context, status_code=status.HTTP_400_BAD_REQUEST)

    # Determine next step
    if phase_number == 2: # Special redirect for phase 2 to allow adding more "etapas"
        redirect_url = request.url_for("render_wizard_phase", interview_id=interview_id, phase_number=2)
    elif phase_number < 5: # total_phases = 5
        next_phase_number = phase_number + 1
        redirect_url = request.url_for("render_wizard_phase", interview_id=interview_id, phase_number=next_phase_number) # Corrected name
    else: # Last phase (5) submitted, go to review page
        redirect_url = request.url_for("render_wizard_review_page", interview_id=interview_id) # Corrected name

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{interview_id}/review", response_class=HTMLResponse, name="get_wizard_review_page")
async def get_wizard_review_page(
    request: Request,
    interview_id: UUID,
    db_interview: models.Interview = Depends(get_wizard_interview_and_check_owner),
    session: AsyncSession = Depends(get_async_session), # For fetching all answers
    current_user: models.User = Depends(current_active_user)
):
    """
    Renders the review page for an interview, showing a summary of all answers.
    """
    all_answers_raw = await crud.get_answer_blocks_by_interview_id(session=session, interview_id=interview_id)

    # Organize answers by phase for easier display in template
    all_answers_by_phase: Dict[int, Dict[str, Any]] = {
        block.phase: block.json_payload for block in all_answers_raw
    }

    context = {
        "request": request,
        "interview": db_interview,
        "all_answers_by_phase": all_answers_by_phase,
        "current_user": current_user,
        "total_phases": 5
    }
    return templates.TemplateResponse("wizard/review.html", context)


# This router needs to be included in main.py
# Example: app.include_router(wizard_router, prefix="/wizard", tags=["Wizard"])

# To make request.state.current_user available:
# Add a middleware or ensure current_active_user dependency populates it.
# FastAPI-Users might do this if configured. If not, a simple middleware:
#
# @app.middleware("http")
# async def add_user_to_state(request: Request, call_next):
#     try:
#         user = await current_active_user(request) # This won't work directly in middleware like this
                                                # Needs proper dependency resolution context.
#         request.state.current_user = user
#     except Exception:
#         request.state.current_user = None
#     response = await call_next(request)
#     return response
#
# A better way is to pass `current_user` explicitly to template context from each route, as done above.
# This avoids complexity with middleware and dependency injection.

# Need to import `select` from `sqlmodel` for the query in get_wizard_phase
from sqlmodel import select
# Need to import `Response` from `fastapi` for `RedirectResponse`
# (already imported `RedirectResponse` directly)
# Need to import `Form` from `fastapi` if using it for specific fields, but `request.form()` is used here.
# Need to import `Any` and `Dict` from `typing`. (already imported)
# `Jinja2Templates` instance is imported from `app.main` as `templates`.
# `HTMLResponse` is from `fastapi.responses`. (already imported)
# `RedirectResponse` is from `fastapi.responses`. (already imported)
# `status` from `fastapi`. (already imported)
# `APIRouter`, `Depends`, `HTTPException` from `fastapi`. (already imported)
# `UUID` from `uuid`. (already imported)
# `AsyncSession` from `sqlmodel.ext.asyncio.session`. (already imported)
# `crud`, `models`, `schemas` from `app`. (already imported)
# `get_async_session` from `app.db`. (already imported)
# `current_active_user` from `app.users`. (already imported)
# `templates` instance from `app.main`. (already imported)

# The `request.url_for(...)` needs the route functions to have a `name` parameter if not automatically inferred.
# I added `name="get_wizard_review_page"` to the review route for clarity.
# FastAPI usually infers names from function names.
# The `get_wizard_phase` will be named `get_wizard_phase` by default.
# The `handle_wizard_phase_submission` will be named `handle_wizard_phase_submission`.
# This should be fine for url_for.

# The submit button on review page will POST to `/interviews/{id}/submit` API endpoint.
# That endpoint should then handle the final submission and BPMN generation trigger.
# It might then redirect to a "completed" page or back to the interview list.
# This wizard router primarily handles rendering the phases and collecting data.
# Final submission logic is in `interviews.py` router.
# The "Generate BPMN" button on the review page could be an HTMX POST to that API endpoint.
# e.g. <button hx-post="{{ request.url_for('submit_interview_for_bpmn_generation', interview_id=interview.id) }}" ...>
# The API endpoint `/interviews/{interview_id}/submit` then needs to handle HTMX redirect.
# If it returns JSON (InterviewRead), HTMX can redirect client-side using HX-Redirect header from server,
# or the wizard's review page button can specify `hx-redirect` after successful POST.
# Or, server can return a `RedirectResponse` directly. The API currently returns `InterviewRead`.
# For HTMX, if the API returns a `RedirectResponse`, HTMX will follow it.
# So, the `/interviews/{id}/submit` endpoint in `interviews.py` might need to return a RedirectResponse
# to, say, `/interviews/{id}` (the detail page) or a new "thank you/processing" page.
# For now, it returns JSON. This might need adjustment for seamless HTMX flow.
# User's guidance: "standard redirects". So, API should return `RedirectResponse`.
# I'll modify the `submit_interview_for_bpmn_generation` in `interviews.py` router later.
# For now, this wizard router sets up the data collection flow.
