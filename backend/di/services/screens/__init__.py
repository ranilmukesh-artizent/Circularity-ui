"""What the screens show (docs/backend-steps.md, B14): what each page shows, already scoped to the signed-in account.

One module per area (home, command, product, case, orchestration, analytics, audit, reference, integration, mcp,
access, workflows), mirroring the frontend facade files in frontend/src/api/*.ts. Their endpoints are in
di.routes.screens, one module per area. Each module's docstring maps the facade functions it serves to its endpoints,
for the frontend switch-over (B17). Formatting (money, percentages, dates for display) stays in the frontend; the
services return data.
"""
