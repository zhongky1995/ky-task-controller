"""Checked-in capability registry for shadow routing."""

from .loader import (
    CapabilityRegistry,
    CapabilitySpec,
    RegistryValidationError,
    ScenarioPack,
    load_registry,
)

__all__ = [
    "CapabilityRegistry",
    "CapabilitySpec",
    "RegistryValidationError",
    "ScenarioPack",
    "load_registry",
]
