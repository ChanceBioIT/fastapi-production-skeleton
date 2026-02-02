from pydantic import BaseModel, Field, field_validator

class SeqTaskParams(BaseModel):
    sequence: str = Field(..., description="DNA Sequence", min_length=1)
    operation: str = Field(..., description="reverse_complement or gc_content")

    @field_validator('sequence')
    @classmethod
    def validate_dna(cls, v: str) -> str:
        if not set(v.upper()).issubset({'A', 'T', 'C', 'G', 'N'}):
            raise ValueError("Sequence contains invalid bases")
        return v.upper()
    
    @field_validator('operation')
    @classmethod
    def validate_opt(cls, v:str) -> str:
        if v.lower() not in ("reverse_complement", "gc_content"):
            raise ValueError("operation only supports reverse_complement or gc_content")
        return v.lower()