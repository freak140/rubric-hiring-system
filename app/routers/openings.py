from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_template_context, set_flash
from app.models.applications import Application
from app.models.enums import AppRole, OpeningStatus, RoleType, ScorecardItemKind
from app.models.openings import RoleOpening
from app.models.scorecards import Scorecard, ScorecardItem
from app.models.users import User
from app.services import permissions
from app.services.audit import log_event
from app.services.workflow import WorkflowError, approve_scorecard, assert_scorecard_editable

router = APIRouter(prefix="/openings", tags=["openings"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_openings(
    status: str | None = None,
    role_type: str | None = None,
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    query = select(RoleOpening).options(selectinload(RoleOpening.hiring_manager))
    if status:
        query = query.where(RoleOpening.status == OpeningStatus(status))
    if role_type:
        query = query.where(RoleOpening.role_type == RoleType(role_type))
    openings = db.scalars(query.order_by(RoleOpening.id.desc())).all()
    return templates.TemplateResponse(
        context["request"],
        "openings/list.html",
        {
            **context,
            "openings": openings,
            "statuses": list(OpeningStatus),
            "role_types": list(RoleType),
            "selected_status": status,
            "selected_role_type": role_type,
            "can_create": permissions.can_create_opening(context["current_user"]),
        },
    )


@router.get("/new")
def new_opening_form(context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    if not permissions.can_create_opening(context["current_user"]):
        raise HTTPException(status_code=403, detail="You cannot create openings.")
    principals = db.scalars(select(User).where(User.app_role == AppRole.principal).order_by(User.name)).all()
    return templates.TemplateResponse(
        context["request"],
        "openings/create.html",
        {**context, "role_types": list(RoleType), "principals": principals},
    )


@router.post("")
def create_opening(
    title: str = Form(...),
    role_type: str = Form(...),
    department: str = Form(...),
    hiring_manager_id: int | None = Form(None),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    current_user = context["current_user"]
    if not permissions.can_create_opening(current_user):
        raise HTTPException(status_code=403, detail="You cannot create openings.")

    manager_id = current_user.id if current_user.app_role == AppRole.principal else hiring_manager_id
    if not manager_id:
        raise HTTPException(status_code=400, detail="A hiring manager is required.")

    opening = RoleOpening(
        title=title.strip(),
        role_type=RoleType(role_type),
        department=department.strip(),
        status=OpeningStatus.draft,
        hiring_manager_id=manager_id,
    )
    db.add(opening)
    db.flush()
    log_event(db, current_user, "opening.create", "RoleOpening", opening.id, details={"title": opening.title})
    db.commit()

    response = RedirectResponse(url=f"/openings/{opening.id}", status_code=303)
    set_flash(response, "success", f"Opening '{opening.title}' created.")
    return response


def _load_opening(db: Session, opening_id: int) -> RoleOpening:
    opening = db.get(
        RoleOpening,
        opening_id,
        options=[
            selectinload(RoleOpening.hiring_manager),
            selectinload(RoleOpening.scorecard).selectinload(Scorecard.items),
            selectinload(RoleOpening.scorecard).selectinload(Scorecard.approved_by),
            selectinload(RoleOpening.applications).selectinload(Application.candidate),
        ],
    )
    if opening is None:
        raise HTTPException(status_code=404, detail="Opening not found.")
    return opening


@router.get("/{opening_id}")
def opening_detail(opening_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]

    pipeline: dict[str, list[Application]] = {}
    for application in opening.applications:
        pipeline.setdefault(application.stage.value, []).append(application)

    return templates.TemplateResponse(
        context["request"],
        "openings/detail.html",
        {
            **context,
            "opening": opening,
            "scorecard": opening.scorecard,
            "pipeline": pipeline,
            "item_kinds": list(ScorecardItemKind),
            "can_manage_scorecard": permissions.can_manage_scorecard(current_user, opening),
            "can_add_candidate": permissions.can_add_candidate(current_user),
        },
    )


@router.post("/{opening_id}/scorecard")
def update_scorecard_mission(
    opening_id: int,
    mission: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    if not permissions.can_manage_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot edit this scorecard.")

    try:
        if opening.scorecard is None:
            new_scorecard = Scorecard(opening=opening, mission=mission.strip())
            db.add(new_scorecard)
            opening.scorecard = new_scorecard
            db.flush()
            log_event(db, current_user, "scorecard.create", "Scorecard", opening.scorecard.id)
        else:
            assert_scorecard_editable(opening.scorecard)
            opening.scorecard.mission = mission.strip()
            log_event(db, current_user, "scorecard.edit_mission", "Scorecard", opening.scorecard.id)
        db.commit()
        response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
        set_flash(response, "success", "Scorecard mission saved.")
    except WorkflowError as exc:
        db.rollback()
        response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
        set_flash(response, "error", str(exc))
    return response


@router.post("/{opening_id}/scorecard/items")
def add_scorecard_item(
    opening_id: int,
    kind: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    measure: str | None = Form(None),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    if not permissions.can_manage_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot edit this scorecard.")

    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    try:
        if opening.scorecard is None:
            raise WorkflowError("Set the scorecard mission before adding items.")
        assert_scorecard_editable(opening.scorecard)
        next_position = max([i.position for i in opening.scorecard.items], default=-1) + 1
        item = ScorecardItem(
            scorecard=opening.scorecard,
            kind=ScorecardItemKind(kind),
            title=title.strip(),
            description=description.strip(),
            measure=(measure or "").strip() or None,
            position=next_position,
        )
        db.add(item)
        db.flush()
        log_event(db, current_user, "scorecard_item.add", "ScorecardItem", item.id, details={"title": item.title})
        db.commit()
        set_flash(response, "success", f"Added '{item.title}'.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{opening_id}/scorecard/items/{item_id}")
def edit_scorecard_item(
    opening_id: int,
    item_id: int,
    title: str = Form(...),
    description: str = Form(...),
    measure: str | None = Form(None),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    if not permissions.can_manage_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot edit this scorecard.")

    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    item = next((i for i in opening.scorecard.items if i.id == item_id), None) if opening.scorecard else None
    if item is None:
        set_flash(response, "error", "Scorecard item not found.")
        return response
    try:
        assert_scorecard_editable(opening.scorecard)
        item.title = title.strip()
        item.description = description.strip()
        item.measure = (measure or "").strip() or None
        log_event(db, current_user, "scorecard_item.edit", "ScorecardItem", item.id, details={"title": item.title})
        db.commit()
        set_flash(response, "success", "Item updated.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{opening_id}/scorecard/items/{item_id}/delete")
def delete_scorecard_item(
    opening_id: int,
    item_id: int,
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    if not permissions.can_manage_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot edit this scorecard.")

    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    item = next((i for i in opening.scorecard.items if i.id == item_id), None) if opening.scorecard else None
    if item is None:
        set_flash(response, "error", "Scorecard item not found.")
        return response
    try:
        assert_scorecard_editable(opening.scorecard)
        log_event(db, current_user, "scorecard_item.delete", "ScorecardItem", item.id, details={"title": item.title})
        db.delete(item)
        db.commit()
        set_flash(response, "success", "Item removed.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{opening_id}/scorecard/items/{item_id}/move")
def move_scorecard_item(
    opening_id: int,
    item_id: int,
    direction: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    if not permissions.can_manage_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot edit this scorecard.")

    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    try:
        assert_scorecard_editable(opening.scorecard)
        items = sorted(opening.scorecard.items, key=lambda i: i.position)
        idx = next((i for i, item in enumerate(items) if item.id == item_id), None)
        if idx is None:
            raise WorkflowError("Scorecard item not found.")
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(items):
            items[idx].position, items[swap_idx].position = items[swap_idx].position, items[idx].position
        db.commit()
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{opening_id}/status")
def update_opening_status(
    opening_id: int,
    status: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    if not permissions.can_manage_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot change this opening's status.")
    old_status = opening.status
    opening.status = OpeningStatus(status)
    log_event(
        db, current_user, "opening.status_change", "RoleOpening", opening.id,
        details={"from": old_status.value, "to": opening.status.value},
    )
    db.commit()
    set_flash(response, "success", f"Opening marked {opening.status.value}.")
    return response


@router.post("/{opening_id}/scorecard/approve")
def approve_scorecard_route(opening_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    if not permissions.can_approve_scorecard(current_user, opening):
        raise HTTPException(status_code=403, detail="You cannot approve this scorecard.")
    try:
        approve_scorecard(db, opening.scorecard, current_user)
        db.commit()
        set_flash(response, "success", "Scorecard approved.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response
