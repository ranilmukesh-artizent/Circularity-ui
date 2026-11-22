"""Siemens Teamcenter 14 mock (docs/backend-steps.md, B5b): the demo's PLM source (SOURCES.plm).

Teamcenter Services (SOA) over HTTP/JSON under /teamcenter/tc/JsonRestServices (see routes.py): session login with the
JSESSIONID cookie, saved queries, getProperties, GRM relation expansion, getItemFromId, setProperties.
Data in Postgres schema `teamcenter` (seed.py): Items, ItemRevisions with release status, alternate approvals,
per-asset compatibility checks.

Documentation followed
    The Teamcenter Services Guide and Services Reference (soa_api_reference, shipped with Teamcenter and on Siemens
        Support Center, https://support.sw.siemens.com, behind a login). No public page could be fetched while building
        this mock; the names below are those of the Services Reference and the published client samples.
    Service and operation names and their input/output structures: Core 2011-06 Session.login (credentials with the
        documented "descrimator" field), Core 2006-03 Session.logout, Core 2007-01 Session.getTCSessionInfo,
        Query 2006-03 SavedQuery.getSavedQueries / describeSavedQueries, Query 2008-06 SavedQuery.executeSavedQueries,
        Core 2006-03 DataManagement.getProperties, Core 2007-09 DataManagement.expandGRMRelationsForPrimary,
        Core 2007-01 DataManagement.getItemFromId, Core 2010-09 DataManagement.setProperties.
    The JSON binding: POST /tc/JsonRestServices/<Library>-<yyyy>-<mm>-<Port>/<operation> with {"header", "body"};
        responses carry ".QName"; ServiceData with plain / modelObjects / updated / partialErrors; model objects with
        uid, className, type and props {dbValues, uiValues}.
    Standard business objects and properties: Item (item_id, object_name, revision_list), ItemRevision
        (item_revision_id, items_tag, release_status_list, date_released), ReleaseStatus ("TCM Released"),
        last_mod_date / creation_date / owning_user / owning_group, the "Item..." and "Item Revision..." saved queries
        and their entries (Item ID, Name, Type, Revision, Release Status, Modified After / Before).

Demo credentials (auth.py): di_connector / Circularity-demo-tc-1 (group Engineering, role Designer); infodba / infodba.

Business rules
    - A released object (an ItemRevision with a release status) cannot be modified (setProperties partial error).
    - setProperties checks optimistic locking (timestamp = last_mod_date), list-of-values (nf0ConfigStatus,
      nf0AltApproved, nf0Approved, nf0Compatibility) and which properties are modifiable; a change stamps
      last_mod_date with the simulated clock and emits com.siemens.teamcenter.<type>.modified.
    - Saved queries take wildcards (*) and "Modified After" / "Modified Before" (strictly after / before).

ASSUMPTION: Teamcenter has no out-of-the-box object for "this asset's configuration was checked against the design";
    the customer's model is assumed to hold it as a custom business object Nf0CompatCheck (prefix nf0 = Northfield),
    with string LOV properties nf0ConfigStatus, nf0AltApproved (Y/N), nf0Compatibility, nf0CompatibleItems,
    nf0TargetUse, nf0CheckedAt and a reference nf0DesignRevision to the ItemRevision.
ASSUMPTION: approved alternates (with a reason) are a custom GRM relation Nf0AltApproval (primary = item, secondary =
    alternate; nf0Approved Y/N, nf0Reason, nf0EffectiveDate), because global alternates carry no approval or reason.
ASSUMPTION: the BOM reference, configuration properties and variants are custom ItemRevision properties nf0BomRef,
    nf0ConfigProps ("Name=Value" strings) and nf0Variants; asset class, product, family and manufacturers are custom
    Item properties nf0AssetClass, nf0Product, nf0Family, nf0Manufacturers.
ASSUMPTION: the custom saved queries "Nf0 Compatibility Checks" (Asset ID, Item ID, Configuration Status, Modified
    After/Before) and "Nf0 Alternate Approvals" (Primary Item ID, Approved, Modified After/Before) exist.
ASSUMPTION: SOA exceptions are returned with HTTP 200 and the serialised exception (".QName" ...Exceptions.<Kind>,
    code, level, message); codes used: 515143 invalid credentials (as Teamcenter logs it), 515117 not logged in /
    session expired, 515001 object not found, 38015 property not defined, 515034 released object, 515035 property not
    modifiable, 214016 stale object, 54060 not in the LOV, 2140xx malformed input. An unknown operation answers 404.
ASSUMPTION: the server's time zone is UTC; dbValues of dates are ISO 8601 with offset, uiValues "dd-Mon-yyyy HH:mm";
    query dates are accepted as "dd-Mon-yyyy HH:mm[:ss]" or ISO 8601.
ASSUMPTION: sessions live in the mock's memory, idle timeout 30 minutes; the property policy in the request header is
    accepted but not applied (getProperties names the properties explicitly).
ASSUMPTION: earlier revisions keep their "TCM Released" status (Teamcenter does not supersede automatically).
"""

from sim.core.mock import Mock
from sim.vendors.teamcenter.routes import router
from sim.vendors.teamcenter.seed import ensure, reset

MOCK = Mock("plm", router, ensure, reset, "Siemens Teamcenter")
