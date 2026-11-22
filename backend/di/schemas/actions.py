"""Request bodies of the action and journal endpoints (di.routes.actions). An action's own input is a JSON object
checked by the action pipeline (di.services.actions.pipeline), not a schema here."""

from pydantic import BaseModel


class Undo(BaseModel):
    seqs: list[int]
