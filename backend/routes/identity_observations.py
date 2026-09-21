"""Administrator review of observations; raw capture secrets never leave here."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config import db
from utils.auth import get_current_user, require_role
from services.identity_observations import (
    ObservationConflict, ObservationMissing, public_observation,
    observation_suggestions, review_observation,
)

router = APIRouter(prefix="/api/admin/identity-observations", tags=["Identity Review"],
                   dependencies=[Depends(require_role(["admin"]))])


class ReviewRequest(BaseModel):
    revision: int = Field(ge=0)
    decision: Literal["link", "new_person", "defer"]
    candidate_id: str | None = Field(default=None, min_length=1, max_length=256)
    reason: str = Field(min_length=10, max_length=2000)


@router.get("")
async def list_observations(
    status: Literal["unresolved", "deferred", "linked", "resolving", "all"] = "unresolved",
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    query = {} if status == "all" else {"status": {"$in": ["unresolved", "resolving"]}} if status == "unresolved" else {"status": status}
    rows = await db.identity_observations.find(query).sort("observed_at", -1).limit(limit).max_time_ms(3000).to_list(limit)
    return {"items": [public_observation(row) for row in rows], "limit": limit}


@router.get("/{observation_id}")
async def get_observation(observation_id: str, user: dict = Depends(get_current_user)):
    doc = await db.identity_observations.find_one({"_id": observation_id})
    if not doc:
        raise HTTPException(404, "Observation not found")
    # Suggestions are recomputed for display; the original capture decision
    # remains unchanged for reproducibility. No review state is mutated by GET.
    result = public_observation(doc, detail=True)
    result["resolution"] = await observation_suggestions(db, doc["snapshot"])
    return result


@router.post("/{observation_id}/review")
async def submit_review(observation_id: str, request: ReviewRequest, user: dict = Depends(get_current_user)):
    try:
        doc = await review_observation(db, observation_id, request.model_dump(), user)
    except ObservationMissing as exc:
        raise HTTPException(404, str(exc)) from None
    except ObservationConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except PermissionError:
        raise HTTPException(403, "Administrator access required") from None
    except Exception:
        raise HTTPException(503, "Review persistence unavailable; refresh before retrying") from None
    return public_observation(doc, detail=True)
