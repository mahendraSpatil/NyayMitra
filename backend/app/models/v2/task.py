from datetime import datetime

from pydantic import BaseModel


class TaskCompleteResponse(BaseModel):
    taskId: str
    completed: bool
    completedAt: datetime | None
