# backend/app/crud/__init__.py
"""
CRUD operations package for the application.
This module re-exports the CRUD operations from the underlying modules.
"""

from .crud_job import job
from .crud_user import user

# Define what should be available when importing from this package
__all__ = ["job", "user"]
