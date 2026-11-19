import os

# Tests drive the scheduler and the webhook sender themselves (sim.scheduler.tick, sim.webhooks.deliver),
# so the background loops stay off in the app instances that tests start.
os.environ.setdefault("SIM_BACKGROUND", "false")
