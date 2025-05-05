# backend/app/schemas/user.py
import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr, Field

# --- Base Schemas from fastapi-users ---
# These provide the standard fields. We inherit from them.

class UserRead(schemas.BaseUser[uuid.UUID]):
    # Inherits id, email, is_active, is_superuser, is_verified
    # Add our custom fields that should be readable
    role: Literal["admin", "standard"]
    created_at: datetime
    updated_at: datetime

    # Example of hiding a field from the read schema if needed:
    # is_verified: bool = Field(..., exclude=True)


class UserCreate(schemas.BaseUserCreate):
    # Inherits email, password
    # Add custom fields required during creation, if any.
    # The 'role' could be set here, but often it's better handled
    # by admin logic or defaults, rather than direct user input on creation.
    # We rely on the DB default 'standard' for role.
    # If OPEN_SIGNUP=False, this schema might only be used by admins.
    pass


class UserUpdate(schemas.BaseUserUpdate):
    # Inherits password (optional)
    # Add custom fields that can be updated by the user or admin.
    # Standard users likely shouldn't update their own role.
    # Admins would need a separate mechanism or schema.
    # We'll handle admin role updates via a dedicated endpoint later.
    email: Optional[EmailStr] = None # Allow email update if needed
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_verified: Optional[bool] = None
    # Do NOT allow role update via this standard schema


# --- Custom Schemas (if needed for specific endpoints) ---

class AdminUserUpdate(BaseModel):
    """Schema specifically for Admins updating other users."""
    # Define fields an admin IS allowed to change
    email: Optional[EmailStr] = None
    role: Optional[Literal["admin", "standard"]] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None # Keep this aligned with 'role'
    is_verified: Optional[bool] = None

    # Note: We might need logic in the update endpoint to ensure
    # if role='admin', then is_superuser=True, and vice-versa.
    # Or decide if 'role' completely replaces the concept of 'is_superuser'.
    # For now, allow updating both, but consistency logic is needed.
