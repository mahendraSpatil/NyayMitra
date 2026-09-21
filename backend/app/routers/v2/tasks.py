import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db.base import get_db
from ...db.models import Task
from ...dependencies import CurrentUser, require_task_owner
from ...models.v2.task import TaskCompleteResponse
from ...services.v2.connections import manager as ws_manager

router = APIRouter()


@router.patch("/tasks/{task_id}/complete", response_model=TaskCompleteResponse)
def complete_task(
    task_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_task_owner),
    db: Session = Depends(get_db),
) -> TaskCompleteResponse:
    """The field restriction firestore.rules used to enforce
    (affectedKeys().hasOnly(['completed', 'completedAt'])) has no
    Postgres/SQLAlchemy equivalent to declare — there's no partial-update
    rule layer any more, only what this route chooses to write. So it's
    enforced structurally instead: this route takes no request body at
    all, and the only two columns it ever touches are completed and
    completed_at. There's nothing else here to accidentally overwrite.
    """
    task = db.get(Task, task_id)
    task.completed = True
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    ws_manager.broadcast_user_sync(current_user.id, {"type": "tasks_changed"})
    return TaskCompleteResponse(taskId=str(task.id), completed=task.completed, completedAt=task.completed_at)
