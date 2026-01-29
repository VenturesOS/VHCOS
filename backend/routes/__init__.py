"""
VHC Talent OS - Routes Module
"""
from .auth import auth_router
from .public import public_router
from .files import files_router
from .admin import admin_router
from .jobs import jobs_router
from .candidates import candidates_router
from .applications import applications_router
from .settings import settings_router
