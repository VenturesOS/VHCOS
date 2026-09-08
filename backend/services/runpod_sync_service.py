"""Retired integration compatibility responses. No network or environment access.

Kept only for older monitoring clients; never scheduled or used for inference.
"""
def get_snapshot():
    return {"status": "retired", "enabled": False, "vllm_reachable": False,
            "message": "Retired provider removed. Use the NVIDIA → Nemotron Super 120B → Emergent chain."}


async def manual_sync_now():
    return get_snapshot()