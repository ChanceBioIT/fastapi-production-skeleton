from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional

class TaskPlugin(ABC):
    @property
    @abstractmethod
    def task_type(self) -> str:
        pass

    @abstractmethod
    async def validate_params(self, params: dict) -> BaseModel:
        pass

    @abstractmethod
    def execute(self, task_id: int, params: dict) -> dict:
        pass
    
    @property
    def is_sync(self) -> Optional[bool]:
        """
        Plugin-specified sync execution mode.
        
        If a non-None value is returned, the is_sync passed at submit time is ignored.
        If None is returned, the is_sync passed at submit time is used.
        
        Returns:
            Optional[bool]: Whether to run synchronously; None means use submit-time parameter
        """
        return None
