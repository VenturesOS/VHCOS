"""
Bootstrap package — app startup wiring split from server.py.

Public surface:
    from bootstrap.routers import all_routers, route_import_failures, log_system_error
    from bootstrap.lifespan import lifespan
    from bootstrap.middleware import register_middleware, register_exception_handler

server.py stays thin: create FastAPI, call these three, run.
"""
