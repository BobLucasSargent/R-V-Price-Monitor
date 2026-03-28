"""R&V IPC — Collector registry with auto-discovery."""
from collectors.base import BaseCollector

_REGISTRY: dict[str, type[BaseCollector]] = {}


def register_collector(cls):
    """Decorator to register a collector class."""
    _REGISTRY[cls.collector_id] = cls
    return cls


def get_collector(collector_id: str) -> BaseCollector:
    cls = _REGISTRY.get(collector_id)
    if cls is None:
        raise KeyError(f"Collector '{collector_id}' not found. Available: {list(_REGISTRY)}")
    return cls()


def get_all_collectors() -> list[BaseCollector]:
    return [cls() for cls in _REGISTRY.values()]


def list_collectors() -> list[str]:
    return list(_REGISTRY.keys())
