"""
Job business logic service.
Helpers for job ID generation and other job-related operations.
"""
from datetime import datetime, timezone

from config import db


async def generate_job_public_id() -> str:
    """
    Generate a unique job public ID in format: VHC/YYYY/NNNN
    - Prefix: VHC
    - Year: Current calendar year
    - Sequence: 4-digit number, resets every year
    """
    current_year = datetime.now(timezone.utc).year

    counter = await db.job_sequences.find_one_and_update(
        {"year": current_year},
        {"$inc": {"sequence": 1}},
        upsert=True,
        return_document=True
    )

    sequence = counter.get("sequence", 1)
    return f"VHC/{current_year}/{sequence:04d}"
