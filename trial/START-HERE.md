# Circularity Decision Workbench: trial

Circularity decides what to do with an industrial asset that comes back at the end of a lease (redeploy, resell,
re-lease, recover parts, recycle or exit) and hands the approved decision to the company's systems. This package runs
the whole app on your own computer. Nothing is sent anywhere: the company, its customers, its cases and the
enterprise systems Circularity talks to are all simulated on your machine.

## What you need

- **Docker**: Docker Desktop on Windows or macOS, or Docker Engine with the Compose plugin on Linux.
  Start it before you go on.
- About **4 GB of free memory** for Docker and **3 GB of free disk space**.
- A web browser (Chrome, Edge, Firefox or Safari).

No internet connection is needed after you have this folder, unless you add a language-model key (see below).

## Start

| | Windows | macOS, Linux |
|---|---|---|
| Start | double-click **start.cmd** | `bash start.sh` in a terminal in this folder |
| Stop (keeps your data) | **stop.cmd** | `bash stop.sh` |
| Back to the starting demo data | **reset.cmd** | `bash reset.sh` |
| Is it running? | **status.cmd** | `bash status.sh` |
| Remove it from Docker | **uninstall.cmd** | `bash uninstall.sh` |

The first start loads the app into Docker and prepares the demo data; it takes a few minutes. Later starts take
under a minute. When it's ready, the script prints the address, **http://localhost:5173**, and on Windows opens it.

## Sign in

Use one of these IDs and **any password**:

| ID | Role |
|---|---|
| `planner.a` (or `ops`) | Planner for Customer A. Owns the example case RT-1048. |
| `planner.b`, `planner.c` | Planners for Customers B and C |
| `approver` | Approver |
| `engineer` | Engineer |
| `finance` | Finance |
| `developer` | Developer (connections, workflows, agents) |
| `exec` | Executive (read only) |
| `warehouse1`, `warehouse2` | Warehouse managers |
| `admin` | Admin (everything) |

Switch account from the menu at the top right.

## A 15-minute tour

1. **As `planner.a`**: open **Home**, then the case **RT-1048** (a returned motor). See the evidence, the routes it
   was valued on and the recommendation. Submit the decision for approval.
2. **As `approver`**: open **Approvals** and approve RT-1048 (or override it with a reason).
3. **As `planner.a`** again: follow the case through execution. The instructions go to the simulated enterprise
   systems and their answers come back on their own over the next minutes.
4. **As `admin`**: open the **Modeler** and add a business rule in plain words, for example *Never recycle grade A*.
   See how the rule would change the open cases before anyone publishes it. A second person must approve it.
5. **As `developer`**: open the **Connection Fabric** to see the systems the cases come from, and **Agents** to see
   what the agents prepared and what they're allowed to do.

The guides in the **guides** folder explain each role, how a case moves through its ten stages, and who approves
what: start with `guides/users/README.md`.

## Good to know

- **A person decides.** Agents and Ask Circularity read, draft and prepare; they never approve, publish or change
  access.
- **Ask Circularity** (the spark button at the top, or Ctrl+J) answers from prepared answers. To have it answer with a
  language model, put a free key from console.groq.com after `GROQ_API_KEY=` in the `.env` file in this folder, then
  stop and start again. Your questions then go to that service.
- **Port taken?** If something else uses port 5173, change `TRIAL_PORT=` in `.env` (created by the first start) and
  start again.
- **Your data** stays in Docker until you run reset or uninstall. Stopping keeps it.
- **The `.env` file** holds this installation's own secrets. Don't share it.

## Organisation sign-in

In this trial, organisation sign-in (OpenID Connect) is **off**: you sign in with the IDs above and any password. A
company that wants its own directory to sign people in sets the `DI_OIDC_ISSUER`, `DI_OIDC_CLIENT_ID`,
`DI_OIDC_CLIENT_SECRET` and `DI_OIDC_REDIRECT_URI` settings on the app's API service and restarts it; directory groups
then map to roles (Admin, Access page). Outside AI clients stay off until an Admin registers them, and Kinective's Legal
team reviews that access before it is offered to a customer.

## If something goes wrong

- *"Docker is not running"*: start Docker Desktop and wait until it says it's running.
- *The app didn't become ready*: run status to see which part is unhealthy, and send us the output of
  `docker compose -f compose.yml logs --tail=200` from this folder.
- *A page looks stuck after a long break*: reload the page; if it persists, stop and start again.
- *You want a clean slate*: run reset.
