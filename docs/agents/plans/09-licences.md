# Plan 9 licences

Every row needs review by Kinective's Legal team before a build that contains the library ships to a customer. The task
that adds a library fills in its pinned version.

| Library | Ecosystem | Licence | Pinned version | Added by task | Why | Legal review |
|---|---|---|---|---|---|---|
| pydantic-ai | PyPI | MIT | 2.73.0 (`pydantic-ai-slim[groq]`, installed at run setup) | P9-2.2 | agent loop behind the AgentLoop port | pending |
| zen-engine | PyPI | MIT (GoRules) | 2.1.7 (`backend/requirements.in`; 2.1.8 is under two weeks old) | P9-4.2 | decision-table evaluator (GoRules ZEN) | pending |
| lightgbm | PyPI | MIT | set by the adding task | P9-6.9 | device price model (quantile boosters) | pending |
| mapie | PyPI | BSD-3-Clause | set by the adding task | P9-6.9 | conformal intervals around the price model | pending |
| lifelines | PyPI | MIT | 0.30.3 (installed at run setup, with pandas 2.3.3) | P9-3.10 | remaining-life model (Weibull AFT and Cox) | pending |
| statsforecast | PyPI | Apache-2.0 | set by the adding task | not named by a task yet; set when first needed | demand forecasting (intermittent-demand models) | pending |
| scipy | PyPI | BSD-3-Clause | set by the adding task | P9-5.3 (first use; see plan note) | `milp` (HiGHS) queue planner; `linear_sum_assignment` matching | pending |
| rapidfuzz | PyPI | MIT | 3.14.6 (installed at run setup) | P9-2.7, P9-8.2 | fuzzy matching of text to pack names; token_set_ratio and Jaro-Winkler on field names for mapping suggestions | pending |
| jsonpatch | PyPI | BSD-3-Clause | set by the adding task | not named by a task yet; set when first needed | RFC 6902 patch view of a customer overlay | pending |
| deepdiff | PyPI | MIT | set by the adding task | not named by a task yet; set when first needed | readable diffs when a pack update or overlay is reviewed | pending |
| pydantic-evals | PyPI | MIT | 2.73.0 (dev lock only) | P9-2.15 | agent evals in CI with an injection corpus | pending |
| authlib | PyPI | BSD-3-Clause | 1.9.5 (+ joserfc 1.8.0) | P9-8.9 | OIDC sign-in beside the demo sign-in | pending |
| scim2-models | PyPI | Apache-2.0 | set by the adding task | P9-8.11 | SCIM provisioning and directory sync | pending |
| pandera | PyPI | MIT | 0.36.0 (`pandera[pandas]`, `backend/requirements.in`; also locks typeguard 4.6.1 (MIT), typing-inspect 0.9.0 (MIT) and mypy-extensions 1.1.0 (MIT), held below 1.2.0 as it is under two weeks old) | P9-7.1 | checks on imported history batches | pending |
| pandas | PyPI | BSD-3-Clause | 2.3.3 (pinned below 3 in `backend/requirements.in`; lifelines needs 2.x; pandera's dependency) | P9-7.1 (first use in the api image beyond lifelines) | data frames pandera checks; a heavy dependency in the api image (image weight, not a container) | pending |
| numpy | PyPI | BSD-3-Clause | 2.5.5 (locked; pandas' dependency) | P9-7.1 | pandas' array library | pending |
| @xyflow/react | npm | MIT | 12.12.1 | P9-8.13 | Studio and Modeler canvas | pending |
| @dagrejs/dagre | npm | MIT | 3.1.3 | P9-8.13 | auto-layout of imported flows | pending |
| @gorules/jdm-editor | npm | MIT | set by the adding task | P9-8.16 | decision table editor in the Modeler | not added by P9-8.16 (native grid editor instead: the library pulls antd 5, monaco and exceljs and needs the shared web_node_modules volume); lead decides |
| jsonschema | PyPI | MIT | 4.26.0 (pinned in `backend/requirements.in`; already locked through `mcp`) | P9-0.7 | validate workflow imports and pack files | pending |
