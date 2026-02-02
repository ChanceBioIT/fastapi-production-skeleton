"""
Repository pattern: data access abstraction, decouples service layer from database session.
"""

from .base import BaseRepository, IRepository
from .unit_of_work import UnitOfWork

__all__ = ["BaseRepository", "IRepository", "UnitOfWork"]

