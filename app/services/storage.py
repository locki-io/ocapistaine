# app/services/storage.py
"""
Redis Storage Service

Re-exports storage classes from mockup module for use as a service.
This provides a cleaner import path for storage functionality.

Usage:
    from app.services.storage import get_storage, ValidationRecord, MockupStorage

Note: The implementation is in app/mockup/storage.py for historical reasons.
"""

from app.mockup.storage import (
    get_storage,
    MockupStorage,
    ValidationRecord,
    MockupKeys,
    MockupTTL,
)

__all__ = [
    "get_storage",
    "MockupStorage",
    "ValidationRecord",
    "MockupKeys",
    "MockupTTL",
]
