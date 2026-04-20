from abc import ABC, abstractmethod


class Intake(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
