"""
Standardized response helpers for API endpoints.
Use for NEW code or routes that already return {"success": bool, ...}.
Do NOT change existing response shapes that the frontend already parses.
"""
from fastapi.responses import JSONResponse


def success_response(data=None, message="OK", status_code=200):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return JSONResponse(content=body, status_code=status_code)


def error_response(message="Error", status_code=400, details=None):
    body = {"success": False, "error": message}
    if details:
        body["details"] = details
    return JSONResponse(content=body, status_code=status_code)
