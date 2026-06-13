from __future__ import annotations

from abc import ABC, abstractmethod

from defiquant.models import Order


class ExecutionAdapter(ABC):
    @abstractmethod
    def execute(self, orders: list[Order]) -> list[str]:
        raise NotImplementedError
