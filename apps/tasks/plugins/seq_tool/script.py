from ..base import TaskPlugin
from .schemas import SeqTaskParams
from framework.exceptions.handler import BusinessException

class SeqToolkitPlugin(TaskPlugin):
    @property
    def task_type(self) -> str:
        return "seq_toolkit"
    
    @property
    def is_sync(self) -> bool:
        return True

    async def validate_params(self, params: dict) -> SeqTaskParams:
        try:
            return SeqTaskParams(**params)
        except Exception as e:
            raise BusinessException(message=f"Parameter validation failed: {str(e)}", code=422)

    def execute(self, task_id: int, params: dict) -> dict:
        """Sync execution logic."""
        seq = params['sequence']
        op = params['operation']
        
        if op == "gc_content":
            gc = (seq.count('G') + seq.count('C')) / len(seq) * 100
            return {"gc_content": round(gc, 2)}
            
        elif op == "reverse_complement":
            complement = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N'}
            rev_comp = "".join(complement.get(base, base) for base in reversed(seq))
            return {"reverse_complement": rev_comp}
        
        raise BusinessException("Unsupported operation type")