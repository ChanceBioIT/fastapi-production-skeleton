"""Task file storage: input params and output results."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from framework.config import settings
from framework.logging.logger import get_logger

logger = get_logger("task_storage")


def get_job_directory(task_type: str, task_id: int, job_id: str) -> Path:
    """Get job workspace path: JOB_WORKSPACE/task_type/task_id_job_id."""
    workspace_root = Path(settings.JOB_WORKSPACE)
    dir_name = f"{task_id}_{job_id}"
    job_dir = workspace_root / task_type / dir_name
    return job_dir


def ensure_job_directory(job_dir: Path) -> None:
    """
    Ensure the task job directory exists.
    
    Args:
        job_dir: Path to the task job directory
    """
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Job directory ensured: {job_dir}")
    except Exception as e:
        logger.error(f"Failed to create job directory {job_dir}: {str(e)}")
        raise


def save_input_params(task_type: str, task_id: int, job_id: str, params: Dict[str, Any]) -> None:
    """Save task input params to input.json."""
    try:
        job_dir = get_job_directory(task_type, task_id, job_id)
        ensure_job_directory(job_dir)
        
        input_file = job_dir / "input.json"
        with open(input_file, 'w', encoding='utf-8') as f:
            json.dump(params, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Input params saved to {input_file}")
    except Exception as e:
        logger.error(f"Failed to save input params for task {task_id}: {str(e)}")
        raise


def load_input_params(task_type: str, task_id: int, job_id: str) -> Optional[Dict[str, Any]]:
    """
    Load task input params from input.json file.
    
    Args:
        task_type: Task type
        task_id: Task ID
        job_id: Task job_id
    
    Returns:
        Task params dict, or None if file does not exist
    """
    try:
        job_dir = get_job_directory(task_type, task_id, job_id)
        input_file = job_dir / "input.json"
        
        if not input_file.exists():
            logger.warning(f"Input file not found: {input_file}")
            return None
        
        with open(input_file, 'r', encoding='utf-8') as f:
            params = json.load(f)
        
        logger.debug(f"Input params loaded from {input_file}")
        return params
    except Exception as e:
        logger.error(f"Failed to load input params for task {task_id}: {str(e)}")
        return None


def save_output_result(task_type: str, task_id: int, job_id: str, result: Dict[str, Any]) -> None:
    """Save task output result to output.json."""
    try:
        job_dir = get_job_directory(task_type, task_id, job_id)
        ensure_job_directory(job_dir)
        
        output_file = job_dir / "output.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Output result saved to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save output result for task {task_id}: {str(e)}")
        raise


def load_output_result(task_type: str, task_id: int, job_id: str) -> Optional[Dict[str, Any]]:
    """Load task output result from output.json. Returns None if file not found."""
    try:
        job_dir = get_job_directory(task_type, task_id, job_id)
        output_file = job_dir / "output.json"
        
        if not output_file.exists():
            logger.debug(f"Output file not found: {output_file}")
            return None
        
        with open(output_file, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        logger.debug(f"Output result loaded from {output_file}")
        return result
    except Exception as e:
        logger.error(f"Failed to load output result for task {task_id}: {str(e)}")
        return None

