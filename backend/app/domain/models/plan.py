from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid
import logging

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "success": "completed",
    "done": "completed",
    "finished": "completed",
    "complete": "completed",
    "error": "failed",
    "failure": "failed",
    "cancelled": "failed",
    "canceled": "failed",
    "in_progress": "running",
    "active": "running",
    "started": "running",
    "waiting": "pending",
    "queued": "pending",
    "idle": "pending",
}

class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

def normalize_status(v):
    if isinstance(v, ExecutionStatus):
        return v
    if isinstance(v, str):
        v_lower = v.lower().strip()
        try:
            return ExecutionStatus(v_lower)
        except ValueError:
            mapped = STATUS_MAP.get(v_lower, "pending")
            logger.warning(f"Unknown status '{v}' mapped to '{mapped}'")
            return ExecutionStatus(mapped)
    return ExecutionStatus.PENDING

class Step(BaseModel):
    model_config = {"extra": "ignore"}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    success: bool = False
    attachments: List[str] = []

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        return normalize_status(v)

    def is_done(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED or self.status == ExecutionStatus.FAILED

class Plan(BaseModel):
    model_config = {"extra": "ignore"}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    goal: str = ""
    language: Optional[str] = "en"
    steps: List[Step] = []
    message: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        return normalize_status(v)

    def is_done(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED or self.status == ExecutionStatus.FAILED
    
    def get_next_step(self) -> Optional[Step]:
        for step in self.steps:
            if not step.is_done():
                return step
        return None
    
    def dump_json(self) -> str:
        return self.model_dump_json(include={"goal", "language", "steps"})
