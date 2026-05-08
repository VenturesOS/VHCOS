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
from .background_jobs import jobs_router as background_jobs_router
from .teams import teams_router
from .referrals import referrals_router
from .commercials import commercials_router
from .analytics import analytics_router
from .revenue import revenue_router
from .employer_routes import employer_router
from .linkedin import router as linkedin_router
