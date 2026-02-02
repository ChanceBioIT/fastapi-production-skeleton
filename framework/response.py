from typing import Any, Optional
from pydantic import BaseModel

class ResponseModel(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None

    @staticmethod
    def success(data: Any = None):
        return {"code": 200, "message": "success", "data": data}

    @staticmethod
    def fail(code: int = 400, message: str = "error", data: Any = None):
        return {"code": code, "message": message, "data": data}
