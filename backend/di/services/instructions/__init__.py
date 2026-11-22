"""Outbound instructions (docs/backend-steps.md, B13b, "the real loop with the mocks").

An approved decision's execution plan (di.services.execution.steps) goes to the enterprise systems one step at a time:

    decision.approve ──> instruction row + `instruction.send` job (step 0)
    worker: send ──> the system's write (di/services/instructions/writers.py), idempotent on the instruction's key
    the system's completion event ──> webhook (di/connectors/webhook.py) ──> match (di/services/instructions/events.py)
        ──> adapter.acknowledge as the system actor, with the system's own reference
        ──> the row is acknowledged and the next step queued (di/services/instructions/queue.py)
    ... until the last step (the S/4 journal entry with the actual costs) closes the case; Finance confirms the outcome.

Modules
    queue    the `instruction` table: queue a step, acknowledge it, resend, simulated steps that are due
    writers  one write per step kind (Sterling, Depot Repair, OTM, Manhattan, S/4), and which kinds are simulated
    send     the `instruction.send` job (retries with backoff through the job queue) and the simulated acknowledgements
    events   which event completes which step, and how an event is matched to its instruction

Switches (di/core/config.py): DI_INSTRUCTIONS (sending is on in the running services, off in the test suite unless a test
turns it on) and DI_CLOCK (di/core/clock.py). With sending off, approval and acknowledgement behave exactly as in the demo.
"""

from di.services.instructions.queue import enabled, on_acknowledged, queue_first, resend

__all__ = ["enabled", "on_acknowledged", "queue_first", "resend"]
