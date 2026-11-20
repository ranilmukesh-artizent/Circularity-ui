"""AWS IoT Core mock: the demo's device telemetry source (SOURCES.iot; docs/backend-steps.md, B5c).

A synthetic stand-in: no real AWS account or service is involved. di starts with this source not provisioned, as in
the demo; the mock itself always answers, so it can be tested and connected (see B5c for how).

Documentation followed
    AWS IoT API reference (control plane, service "iot"):
      https://docs.aws.amazon.com/iot/latest/apireference/API_ListThings.html          (also DescribeThing,
      ListThingGroups, DescribeThingGroup, ListThingsInThingGroup, ListJobs, DescribeJob, ListTopicRules, GetTopicRule)
    AWS IoT data plane (service "iotdata"):
      https://docs.aws.amazon.com/iot/latest/apireference/API_iotdata_GetThingShadow.html (also UpdateThingShadow,
      DeleteThingShadow, ListNamedShadowsForThing, Publish, ListRetainedMessages, GetRetainedMessage)
    Device Shadow documents: https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html
    Rules (SQL, topic(), timestamp(), HTTPS action): https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html
    Signature Version 4: https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html
    Error responses: https://docs.aws.amazon.com/iot/latest/apireference/CommonErrors.html
    Topic design (dt/<application>/<thing>/<type>): AWS whitepaper "Designing MQTT Topics for AWS IoT Core".

Hosts: /aws-iot/iot stands in for iot.ap-south-1.amazonaws.com, /aws-iot/data for the account's ATS data endpoint.
Auth: SigV4 (sigv4.py) in region ap-south-1, service "iot" or "iotdata". Demo IAM users (api.py):
    AKIACIRCULARITYDEMO1 / circularity-demo/aws-iot/K7MDENG+bPxRfiCYDI   the di connector, every action
    AKIACIRCULARITYRDONL / circularity-demo/aws-iot/readonly+R3AD0NLY     a viewer: control-plane reads of things only
    403 MissingAuthenticationTokenException | IncompleteSignatureException | UnrecognizedClientException (unknown key)
    | InvalidSignatureException (bad signature, wrong region or service, more than 15 min clock skew);
    401 UnauthorizedException (the user lacks the action).
Faults (/_sim/faults, system iot) answer in AWS's shape: error 429 -> ThrottlingException "Rate exceeded", other 5xx
    -> InternalFailureException, unavailable -> 503 ServiceUnavailableException, token_expired -> 403
    ExpiredTokenException; latency as for every mock.
Errors: x-amzn-ErrorType header with the code, body {"message"}; 404 ResourceNotFoundException, 400
    InvalidRequestException (bad maxResults or nextToken, bad shadow document), 409 ConflictException (shadow version),
    413 RequestEntityTooLargeException.

The fleet (seed.py): 77 condition-monitoring kits (CMK-3): one per returned motor or pump of the live cases (offline)
and 24 on redeployed or re-leased assets in service (online). Thing attribute assetTag links each to the asset id the
other systems use (cm-mtr-2041 -> MTR-2041, RT-1048's motor). Thing groups northfield-condition-monitoring >
returned-assets > returned-<site>, and in-service-pilot. Shadows: the classic shadow holds configuration and firmware
(desired/reported, so a pending firmware shows as delta); the named shadow "condition" holds what the device measures:
operatingHours, dutyCyclePct, vibrationMmS, vibrationZone, bearingTempC, running, sampleAt, alarms, events (last 5).
Topics: dt/<fleet>/<thing>/telemetry (retained, hourly) and dt/<fleet>/<thing>/events (retained alarm), fleet motors |
pumps. Jobs: fw-2-4-1-rollout (completed), fw-2-5-0-pilot (in progress).

Simulated clock and rules (fleet.py): every simulated hour each online kit reports; the topic rules
circularity_telemetry, circularity_condition_events and circularity_shadow_changes deliver to their HTTPS destination,
which is source-sim's outbox: CloudEvents `aws.iot.rule.<ruleName>` signed with HMAC (sim/webhooks.py), the SELECT
result as data. The pull path for backfill is ListRetainedMessages (lastModifiedTime per topic) + GetThingShadow.

ASSUMPTION: one AWS account (123456789012), region ap-south-1 (the demo's sites are in India).
ASSUMPTION: thing names cm-<asset id>; attribute values follow AWS's character rules, so the tenant is a code
    (customer-a), not its display name.
ASSUMPTION: timestamps as the APIs document them: shadow metadata and timestamps in epoch seconds, retained
    lastModifiedTime in epoch milliseconds, control-plane dates (creationDate, createdAt) as epoch seconds.
ASSUMPTION: shadows and retained messages change on the simulated clock (sim/clock.py), as every mock's data does;
    SigV4's X-Amz-Date is checked against the wall clock, as AWS does.
Left out: certificates and policies, Fleet Indexing / SearchIndex, Device Defender, job executions per thing and
    CreateJob, creating or changing things, groups and rules (the fleet is read-only apart from shadows and Publish),
    MQTT and WebSocket connections (devices are simulated server-side), rule SQL beyond the seeded rules' forms
    (fleet.py), service rate limits (throttling comes only from the fault injection).
"""

from sim.mock import Mock
from sim.vendors.aws_iot import api, seed

MOCK = Mock("iot", api.router, seed.ensure, seed.reset, "AWS IoT Core")
