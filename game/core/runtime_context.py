"""Shared runtime context dataclasses for plugin factories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ValidatorRuntimeContext:
    """Injected shared services for a game plugin validator runner.

    Phase 1 commonly passes the validator neuron directly. This dataclass exists
    so later refactors can move to explicit dependency injection without
    changing plugin interfaces again.
    """

    validator: Any
    services: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MinerRuntimeContext:
    """Injected shared services for miner-side game handlers."""

    miner: Any
    services: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderContext:
    """Reusable provider context (HTTP clients, keys, base URLs, etc.)."""

    name: str
    client: Optional[Any] = None
    settings: Dict[str, Any] = field(default_factory=dict)
