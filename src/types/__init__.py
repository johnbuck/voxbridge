"""
VoxBridge Types Module

Type definitions and schemas for VoxBridge 2.0
"""

from .error_events import ServiceErrorEvent, ServiceErrorType

__all__ = [
    "ServiceErrorEvent",
    "ServiceErrorType",
]
