from __future__ import annotations

from .base import Transform


class TransformRegistry:
    def __init__(self) -> None:
        self._items: dict[str, type[Transform]] = {}

    def register(self, cls: type[Transform]) -> type[Transform]:
        if cls.step_type in self._items:
            raise ValueError(f"duplicate step_type {cls.step_type}")
        self._items[cls.step_type] = cls
        return cls

    def get(self, step_type: str) -> Transform:
        try:
            return self._items[step_type]()
        except KeyError as exc:
            raise KeyError(f"Unknown step type '{step_type}'") from exc

    def has(self, step_type: str) -> bool:
        return step_type in self._items

    def catalog(self) -> list[dict]:
        return [cls.spec() for cls in self._items.values()]


registry = TransformRegistry()
register = registry.register
