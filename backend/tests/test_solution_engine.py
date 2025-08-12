import pytest
from services.solution_engine import SolutionEngine
from models.models import PodEvent, ContainerStatus


class TestSolutionEngine:
    
    @pytest.fixture
    def solution_engine(self):
        """Create SolutionEngine instance"""
        return SolutionEngine()

    @pytest.mark.asyncio
    async def test_get_solution_image_pull_backoff(self, solution_engine):
        """Test solution generation for ImagePullBackOff"""
        reason = "ImagePullBackOff"
        message = "Failed to pull image 'nonexistent:latest'"
        
        solution = await solution_engine.get_solution(reason, message)
        
        assert solution is not None
        assert len(solution) > 0
        assert "image" in solution.lower()

    @pytest.mark.asyncio
    async def test_get_solution_crash_loop_backoff(self, solution_engine):
        """Test solution generation for CrashLoopBackOff"""
        reason = "CrashLoopBackOff"
        message = "Container crashed with exit code 1"
        
        container_status = ContainerStatus(
            name="test-container",
            ready=False,
            restart_count=5,
            image="test:latest",
            state="waiting",
            reason="CrashLoopBackOff",
            message="Container crashed with exit code 1",
            exit_code=1
        )
        
        solution = await solution_engine.get_solution(
            reason, message, container_statuses=[container_status]
        )
        
        assert solution is not None
        assert "restart" in solution.lower() or "crash" in solution.lower()

    @pytest.mark.asyncio
    async def test_get_solution_with_events(self, solution_engine):
        """Test solution generation with pod events"""
        reason = "Pending"
        message = "Pod is pending"
        
        events = [
            PodEvent(
                type="Warning",
                reason="FailedMount",
                message="MountVolume.SetUp failed: secret 'test' not found",
                timestamp="2025-01-01T00:00:00Z"
            )
        ]
        
        solution = await solution_engine.get_solution(reason, message, events=events)
        
        assert solution is not None
        assert "secret" in solution.lower() or "mount" in solution.lower()

    def test_fallback_solution(self, solution_engine):
        """Test fallback solution for unknown failure"""
        reason = "UnknownFailure"
        message = "Something went wrong"
        
        solution = solution_engine._get_fallback_solution(reason, message)
        
        assert solution is not None
        assert "unknown" in solution.lower()

    def test_find_pattern_solution(self, solution_engine):
        """Test pattern-based solution matching"""
        patterns = {
            "not found": "Resource not found solution",
            "access denied": "Access denied solution"
        }
        
        message = "Error: image not found in registry"
        events = []
        
        solution = solution_engine._find_pattern_solution(patterns, message, events)
        
        assert solution == "Resource not found solution"

    def test_enhance_solution_with_context(self, solution_engine):
        """Test solution enhancement with context"""
        base_solution = "Basic pod failure solution"
        reason = "ImagePullBackOff"
        
        enhanced = solution_engine._enhance_solution_with_context(
            base_solution, reason, None, [], []
        )
        
        assert "kubectl describe pod" in enhanced
        assert "docker pull" in enhanced