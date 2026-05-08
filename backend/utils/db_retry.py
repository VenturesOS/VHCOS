"""
VHC Talent OS — MongoDB Write Retry Utility
Handles transient write errors (reconnects, duplicate key on retry, etc.)
"""
import logging
import asyncio
from typing import Any, Callable
from pymongo.errors import (
    AutoReconnect, ConnectionFailure, ServerSelectionTimeoutError,
    DuplicateKeyError, WriteError
)

logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = (AutoReconnect, ConnectionFailure, ServerSelectionTimeoutError)
MAX_RETRIES = 3
BASE_DELAY = 0.5  # seconds


async def retry_write(operation: Callable, *args, retries: int = MAX_RETRIES, **kwargs) -> Any:
    """
    Execute a MongoDB write operation with retry logic.
    Handles transient errors like AutoReconnect and ConnectionFailure.
    """
    last_error = None
    for attempt in range(retries):
        try:
            return await operation(*args, **kwargs)
        except DuplicateKeyError:
            # Not retryable — the write already succeeded on a previous attempt
            logger.debug("[DB_RETRY] DuplicateKeyError — previous write likely succeeded")
            return None
        except WriteError as e:
            # WriteError code 11000 = duplicate key (same as DuplicateKeyError)
            if e.code == 11000:
                logger.debug("[DB_RETRY] WriteError 11000 — previous write likely succeeded")
                return None
            last_error = e
            logger.warning(f"[DB_RETRY] WriteError on attempt {attempt + 1}/{retries}: {e}")
        except RETRYABLE_ERRORS as e:
            last_error = e
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(f"[DB_RETRY] Transient error on attempt {attempt + 1}/{retries}: {e}. Retrying in {delay}s")
            await asyncio.sleep(delay)
        except Exception:
            # Non-retryable error — raise immediately
            raise

    logger.error(f"[DB_RETRY] All {retries} attempts failed. Last error: {last_error}")
    if last_error:
        raise last_error
