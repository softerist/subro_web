# backend/app/schemas/user.py
import uuid
from datetime import datetime
from enum import Enum  # Import Enum
from typing import Literal

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr

# --- Base Schemas from fastapi-users ---
# These provide the standard fields. We inherit from them.


# --- Define UserRole Enum ---
class UserRole(str, Enum):
    ADMIN = "admin"
    STANDARD = "standard"


class UserRead(schemas.BaseUser[uuid.UUID]):
    # Inherits id, email, is_active, is_superuser, is_verified
    # Add our custom fields that should be readable
    role: Literal["admin", "standard"]
    created_at: datetime
    updated_at: datetime

    # Example of hiding a field from the read schema if needed:
    # is_verified: bool = Field(..., exclude=True)


class UserCreate(schemas.BaseUserCreate):
    role: UserRole = UserRole.STANDARD  # Example: default to standard
    is_superuser: bool = False  # Example: default to False
    is_active: bool = True  # Example: default to True
    is_verified: bool = False  # Example: default to False


class UserUpdate(schemas.BaseUserUpdate):
    # Inherits password (optional)
    # Add custom fields that can be updated by the user or admin.
    # Standard users likely shouldn't update their own role.
    # Admins would need a separate mechanism or schema.
    # We'll handle admin role updates via a dedicated endpoint later.
    email: EmailStr | None = None  # Allow email update if needed
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
    # Do NOT allow role update via this standard schema


# --- Custom Schemas (if needed for specific endpoints) ---


class AdminUserUpdate(BaseModel):
    """Schema specifically for Admins updating other users."""

    # Define fields an admin IS allowed to change
    email: EmailStr | None = None
    role: Literal["admin", "standard"] | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None  # Keep this aligned with 'role'
    is_verified: bool | None = None

    # Note: We might need logic in the update endpoint to ensure
    # if role='admin', then is_superuser=True, and vice-versa.
    # Or decide if 'role' completely replaces the concept of 'is_superuser'.
    # For now, allow updating both, but consistency logic is needed.
