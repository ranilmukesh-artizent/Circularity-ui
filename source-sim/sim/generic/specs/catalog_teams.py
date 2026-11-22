"""Microsoft Teams (catalogue): channels and the notification and escalation messages posted in them. Synthetic;
reads like Microsoft Graph (`value`, `$top` / `$skiptoken`, chatMessage fields). OAuth 2.0 client credentials."""

from sim.generic.catalog import PEOPLE, ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

CHANNELS = ("Returns escalations", "Integration alerts", "Remarketing desk")


def seed(s: Seed) -> dict[str, list[dict]]:
    channels = [
        {"id": f"19:{h(c):08x}@thread.tacv2", "displayName": c, "membershipType": "standard",
         "createdDateTime": iso(ago(s, c, days=400))}
        for c in CHANNELS
    ]  # fmt: skip
    messages = []
    for n, f in enumerate(f for f in facts(s) if h(f.id, "teams") % 4 == 0):
        ch = channels[n % len(channels)]
        messages.append(
            {"id": str(1700000000000 + n), "channelId": ch["id"], "messageType": "message",
             "from": {"user": {"displayName": pick(PEOPLE, f.id, "from")}},
             "body": {"contentType": "text", "content": f"{f.id}: {f.readiness}"},
             "createdDateTime": iso(ago(s, f.id, "msg", days=14))}
        )  # fmt: skip
    return {"channels": channels, "messages": messages}


SPEC = Spec(
    source_id="teams",
    title="Microsoft Teams",
    schema="cat_teams",
    base_path="/teams/v1.0",
    auth=Auth("oauth_cc", token_path="/oauth2/v2.0/token"),  # noqa: S106 - a URL path
    paging=Paging(
        "cursor",
        limit_param="$top",
        cursor_param="$skiptoken",
        items_key="value",
        next_key="nextSkipToken",
        total_key=None,
        max_size=50,
    ),
    resources=(
        Resource("channels", "/channels", "id"),
        Resource("messages", "/messages", "id", filters=("channelId", "messageType")),
    ),
    seed=seed,
)
