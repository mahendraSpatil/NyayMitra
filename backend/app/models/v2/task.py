from datetime import datetime

from pydantic import BaseModel


class TaskCompleteResponse(BaseModel):
    taskId: str
    completed: bool
    completedAt: datetime | None


class TaskItem(BaseModel):
    """Matches client/lib/core/models/task.dart's Task.fromApi field
    names.
    """

    id: str
    assignedToUid: str
    caseId: str
    taskType: str
    priority: str
    description: str
    completed: bool
    completedAt: datetime | None
