"""Task API test cases."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from apps.tasks.models import Task, TaskStatus


class TestTaskSubmit:
    """Test task submit API."""
    
    @pytest.mark.asyncio
    async def test_submit_task_success_gc_content(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test submit GC content task successfully."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCGATCG",
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert data["data"] is not None
        
        task_data = data["data"]
        assert task_data["task_type"] == "seq_toolkit"
        assert task_data["status"] == TaskStatus.COMPLETED or task_data["status"] == "completed"
        assert task_data["params"]["sequence"] == "ATCGATCG"
        assert task_data["params"]["operation"] == "gc_content"
        assert task_data["result"] is not None
        assert "gc_content" in task_data["result"]
        assert task_data["user_id"] == sample_user.id
        assert task_data["tenant_id"] == sample_tenant.id
    
    @pytest.mark.asyncio
    async def test_submit_task_success_reverse_complement(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test submit reverse complement task successfully."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCG",
                "operation": "reverse_complement"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"] is not None
        
        task_data = data["data"]
        assert task_data["status"] == TaskStatus.COMPLETED or task_data["status"] == "completed"
        assert task_data["result"] is not None
        assert "reverse_complement" in task_data["result"]
        assert task_data["result"]["reverse_complement"] == "CGAT"
    
    @pytest.mark.asyncio
    async def test_submit_task_invalid_task_type(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """Test submit unsupported task type."""
        payload = {
            "task_type": "invalid_task_type",
            "params": {
                "sequence": "ATCG",
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200  # FastAPI returns 200; error is in data.code
        data = response.json()
        assert data["code"] == 400
        assert "Unsupported task type" in data["message"]
    
    @pytest.mark.asyncio
    async def test_submit_task_invalid_sequence(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """Test submit sequence with invalid bases."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCGX",
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 422
        assert "Parameter validation failed" in data["message"] or "invalid bases" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_submit_task_missing_params(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """Test submit task with missing required params."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCG"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 422
        assert "Parameter validation failed" in data["message"] or "Parameter validation" in data["message"]
    
    @pytest.mark.asyncio
    async def test_submit_task_invalid_operation(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """Test submit unsupported operation type."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCG",
                "operation": "invalid_operation"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 422
        assert "operation only supports" in data["message"] or "Unsupported operation" in data["message"]
    
    @pytest.mark.asyncio
    async def test_submit_task_async_mode(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test async mode submit."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCG",
                "operation": "gc_content"
            },
            "is_sync": False
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"] is not None
        
        task_data = data["data"]
        assert task_data["is_sync"] is False
        assert task_data["status"] == TaskStatus.PENDING or task_data["status"] == "pending"
    
    @pytest.mark.asyncio
    async def test_submit_task_empty_sequence(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """Test submit empty sequence."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "",
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 422
        assert "Parameter validation failed" in data["message"] or "Parameter validation" in data["message"]


class TestTaskValidation:
    """Test task param validation."""
    
    @pytest.mark.asyncio
    async def test_sequence_case_insensitive(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test sequence case insensitive."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "atcg",  # lowercase
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["params"]["sequence"] == "ATCG"
    
    @pytest.mark.asyncio
    async def test_sequence_with_n(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test sequence containing N (unknown base)."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCGN",
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["params"]["sequence"] == "ATCGN"


class TestTaskResults:
    """Test task results."""
    
    @pytest.mark.asyncio
    async def test_gc_content_calculation(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test GC content result correctness."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCG",
                "operation": "gc_content"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        
        result = data["data"]["result"]
        assert "gc_content" in result
        assert abs(result["gc_content"] - 50.0) < 0.01
    
    @pytest.mark.asyncio
    async def test_reverse_complement_result(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        sample_tenant,
        sample_user
    ):
        """Test reverse complement result correctness."""
        payload = {
            "task_type": "seq_toolkit",
            "params": {
                "sequence": "ATCG",
                "operation": "reverse_complement"
            },
            "is_sync": True
        }
        
        response = await client.post("/api/v1/tasks/submit", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        
        result = data["data"]["result"]
        assert "reverse_complement" in result
        # ATCG -> CGAT
        assert result["reverse_complement"] == "CGAT"
