from dataclasses import dataclass
from typing import Protocol
from .errors import PortError

MODULE_API = 1


class GameModule(Protocol):
    api_version: int
    id: str
    version: str
    def identify(self, source: dict) -> dict: ...
    def dependencies(self) -> tuple[str, ...]: ...
    def plan(self, source: dict) -> list[dict]: ...
    def build(self, context: dict): ...
    def verify(self, artifact): ...
    def launch(self, artifact): ...


def require_api(module):
    if module.api_version != MODULE_API:
        raise PortError('MODULE_API', 'Versão incompatível da interface do módulo.')
