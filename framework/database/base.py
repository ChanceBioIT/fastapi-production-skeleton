from abc import ABC, abstractmethod

class BaseDatabaseDriver(ABC):
    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def disconnect(self):
        pass
