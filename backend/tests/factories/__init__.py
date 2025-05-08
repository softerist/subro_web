# backend/tests/factories/__init__.py

# Import the UserFactory from the user_factory.py module within this package
from .user_factory import UserFactory

# Define what names should be exported when using 'from .factories import *'
# (optional but good practice)
__all__ = ["UserFactory"]
