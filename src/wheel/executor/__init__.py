"""Execute a policy-proposed action: validate, place (or dry-run), record."""

from wheel.executor.executor import Executor, ExecutionResult, SafetyError

__all__ = ["Executor", "ExecutionResult", "SafetyError"]
