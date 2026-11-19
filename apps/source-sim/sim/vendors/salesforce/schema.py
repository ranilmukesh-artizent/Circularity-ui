"""The sObjects this org holds, their fields, and the Postgres tables behind them (schema `salesforce`).

One spec drives everything: the tables (one column per field, named as the field), describe, SOQL field resolution
and write validation. Field types are Salesforce's (id, reference, string, picklist, currency, date, datetime, ...).
"""

from dataclasses import dataclass, field

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, MetaData, Numeric, Sequence, String, Table, Text

metadata = MetaData(schema="salesforce")
RECORD_SEQ = Sequence("record_seq", metadata=metadata, start=5_000_000)  # ids of records created through the API

API_VERSION = "59.0"
BASE = f"/services/data/v{API_VERSION}"  # as a Salesforce client sees it (relative to instance_url)


@dataclass(frozen=True)
class Field:
    name: str
    type: str  # Salesforce field type
    label: str
    length: int = 0
    ref: tuple[str, ...] = ()  # referenceTo
    rel: str | None = None  # relationshipName (traversable in SOQL when ref has one target)
    create: bool = True
    update: bool = True
    nillable: bool = True
    picklist: tuple[str, ...] = ()
    default: str | None = None  # default picklist value

    @property
    def custom(self) -> bool:
        return self.name.endswith("__c")

    @property
    def textual(self) -> bool:
        return self.type in ("string", "picklist", "textarea", "email", "phone", "url")


@dataclass(frozen=True)
class SObject:
    name: str
    label: str
    plural: str
    prefix: str
    fields: tuple[Field, ...]
    writable: bool = False  # create and patch allowed through the API
    by_lower: dict[str, Field] = field(default_factory=dict, compare=False)

    def __post_init__(self):
        self.by_lower.update({f.name.lower(): f for f in self.fields})

    def get(self, name: str) -> Field | None:
        return self.by_lower.get(name.lower())

    def relationship(self, name: str) -> Field | None:
        """The single-target reference field behind relationship `name` (e.g. Account → AccountId)."""
        return next((f for f in self.fields if f.rel and f.rel.lower() == name.lower() and len(f.ref) == 1), None)


def _ro(name, type_, label, **kw) -> Field:
    return Field(name, type_, label, create=False, update=False, **kw)


def _system(prefix_label: str) -> tuple[Field, ...]:
    return (
        _ro("Id", "id", f"{prefix_label} ID", length=18, nillable=False),
        _ro("IsDeleted", "boolean", "Deleted", nillable=False),
        _ro("CreatedDate", "datetime", "Created Date", nillable=False),
        _ro("CreatedById", "reference", "Created By ID", length=18, ref=("User",), rel="CreatedBy", nillable=False),
        _ro("LastModifiedDate", "datetime", "Last Modified Date", nillable=False),
        _ro(
            "LastModifiedById", "reference", "Last Modified By ID", length=18, ref=("User",), rel="LastModifiedBy", nillable=False
        ),
        _ro("SystemModstamp", "datetime", "System Modstamp", nillable=False),
    )


def _owner() -> Field:
    return Field("OwnerId", "reference", "Owner ID", length=18, ref=("User",), rel="Owner")


STAGES = ("Prospecting", "Qualification", "Needs Analysis", "Proposal", "Negotiation", "Closed Won", "Closed Lost")
# StageName → (Probability, ForecastCategoryName, IsClosed, IsWon), as in a standard org's sales process
STAGE_RULES = {
    "Prospecting": (10, "Pipeline", False, False),
    "Qualification": (20, "Pipeline", False, False),
    "Needs Analysis": (40, "Pipeline", False, False),
    "Proposal": (75, "Pipeline", False, False),
    "Negotiation": (90, "Commit", False, False),
    "Closed Won": (100, "Closed", True, True),
    "Closed Lost": (0, "Omitted", True, False),
}
TASK_STATUS = ("Not Started", "In Progress", "Completed", "Waiting on someone else", "Deferred")

OBJECTS: dict[str, SObject] = {
    o.name: o
    for o in (
        SObject(
            "User",
            "User",
            "Users",
            "005",
            _system("User")
            + (
                Field("Username", "string", "Username", 80, nillable=False),
                Field("Name", "string", "Full Name", 121, create=False, update=False),
                Field("FirstName", "string", "First Name", 40),
                Field("LastName", "string", "Last Name", 80, nillable=False),
                Field("Email", "email", "Email", 128),
                Field("Alias", "string", "Alias", 8),
                Field("Title", "string", "Title", 80),
                Field("IsActive", "boolean", "Active", nillable=False),
            ),
        ),
        SObject(
            "Account",
            "Account",
            "Accounts",
            "001",
            _system("Account")
            + (
                _owner(),
                Field("Name", "string", "Account Name", 255, nillable=False),
                Field("AccountNumber", "string", "Account Number", 40),
                Field("Type", "picklist", "Account Type", 255, picklist=("Customer - Direct", "Customer - Channel", "Prospect")),
                Field("Industry", "picklist", "Industry", 255, picklist=("Manufacturing", "Energy", "Transportation")),
                Field("BillingCity", "string", "Billing City", 40),
                Field("BillingCountry", "string", "Billing Country", 80),
                Field("Tenant_Key__c", "string", "Tenant Key", 40),
            ),
        ),
        SObject(
            "Contact",
            "Contact",
            "Contacts",
            "003",
            _system("Contact")
            + (
                _owner(),
                Field("AccountId", "reference", "Account ID", 18, ref=("Account",), rel="Account"),
                Field("Name", "string", "Full Name", 121, create=False, update=False),
                Field("FirstName", "string", "First Name", 40),
                Field("LastName", "string", "Last Name", 80, nillable=False),
                Field("Title", "string", "Title", 128),
                Field("Email", "email", "Email", 80),
                Field("Phone", "phone", "Business Phone", 40),
            ),
        ),
        SObject(
            "Contract",
            "Contract",
            "Contracts",
            "800",
            _system("Contract")
            + (
                _owner(),
                Field("AccountId", "reference", "Account ID", 18, ref=("Account",), rel="Account", nillable=False),
                Field("Name", "string", "Contract Name", 80),
                _ro("ContractNumber", "string", "Contract Number", length=30, nillable=False),
                Field(
                    "Status", "picklist", "Status", 40, picklist=("Draft", "In Approval Process", "Activated"), default="Draft"
                ),
                Field("StartDate", "date", "Contract Start Date"),
                Field("ContractTerm", "int", "Contract Term (months)"),
                _ro("EndDate", "date", "Contract End Date"),
                Field("Description", "textarea", "Description", 32000),
                Field("Asset_Id__c", "string", "Asset ID", 40),
                Field("Case_Id__c", "string", "Circularity Case", 20),
                Field("Monthly_Rate__c", "currency", "Monthly Lease Rate"),
            ),
        ),
        SObject(
            "Opportunity",
            "Opportunity",
            "Opportunities",
            "006",
            _system("Opportunity")
            + (
                _owner(),
                Field("AccountId", "reference", "Account ID", 18, ref=("Account",), rel="Account"),
                Field("Name", "string", "Name", 120, nillable=False),
                Field("Type", "picklist", "Opportunity Type", 255, picklist=("Replacement", "Lease", "New Business")),
                Field("StageName", "picklist", "Stage", 255, picklist=STAGES, nillable=False),
                Field("Amount", "currency", "Amount"),
                Field("Probability", "percent", "Probability (%)"),
                _ro("ForecastCategoryName", "picklist", "Forecast Category", length=255),
                Field("CloseDate", "date", "Close Date", nillable=False),
                _ro("IsClosed", "boolean", "Closed", nillable=False),
                _ro("IsWon", "boolean", "Won", nillable=False),
                Field("TotalOpportunityQuantity", "double", "Quantity"),
                Field("ContractId", "reference", "Contract ID", 18, ref=("Contract",), rel="Contract"),
                Field("Description", "textarea", "Description", 32000),
                Field("Case_Id__c", "string", "Circularity Case", 20),
                Field("Asset_Id__c", "string", "Asset ID", 40),
                Field("Site__c", "string", "Delivery Site", 40),
                Field("Lease_Reference__c", "string", "Lease Reference", 20),
            ),
            writable=True,
        ),
        SObject(
            "Task",
            "Task",
            "Tasks",
            "00T",
            _system("Activity")
            + (
                _owner(),
                Field("Subject", "string", "Subject", 255),
                Field("Status", "picklist", "Status", 40, picklist=TASK_STATUS, nillable=False, default="Not Started"),
                Field(
                    "Priority", "picklist", "Priority", 40, picklist=("High", "Normal", "Low"), nillable=False, default="Normal"
                ),
                Field("Type", "picklist", "Type", 40, picklist=("Call", "Email", "Meeting", "Sale", "Other")),
                Field("ActivityDate", "date", "Due Date Only"),
                Field("WhatId", "reference", "Related To ID", 18, ref=("Opportunity", "Account", "Contract"), rel="What"),
                Field("WhoId", "reference", "Name ID", 18, ref=("Contact",), rel="Who"),
                _ro("AccountId", "reference", "Account ID", length=18, ref=("Account",), rel="Account"),
                _ro("IsClosed", "boolean", "Closed", nillable=False),
                Field("Description", "textarea", "Description", 32000),
            ),
            writable=True,
        ),
    )
}
BY_PREFIX = {o.prefix: o for o in OBJECTS.values()}
BY_LOWER = {o.name.lower(): o for o in OBJECTS.values()}


def _column(f: Field) -> Column:
    t = {
        "id": String(18),
        "reference": String(18),
        "boolean": Boolean,
        "date": Date,
        "datetime": DateTime(timezone=True),
        "int": Integer,
        "currency": Numeric(18, 2),
        "double": Numeric(18, 2),
        "percent": Numeric(5, 2),
        "textarea": Text,
    }.get(f.type, String(f.length or 255))
    return Column(f.name, t, primary_key=f.name == "Id", nullable=f.name != "Id")


TABLES: dict[str, Table] = {o.name: Table(o.name.lower(), metadata, *[_column(f) for f in o.fields]) for o in OBJECTS.values()}


# ------------------------------------------------------------------ ids
_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_CHECK = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
POD = "Hs0"  # instance and reserved characters, as in the demo's 001Hs00003AbCdE


def to18(id15: str) -> str:
    """Salesforce's case-safe id: append one checksum character per 5-character chunk."""
    suffix = ""
    for i in range(3):
        chunk = id15[i * 5 : i * 5 + 5]
        suffix += _CHECK[sum(1 << j for j, ch in enumerate(chunk) if "A" <= ch <= "Z")]
    return id15 + suffix


def make_id(prefix: str, n: int) -> str:
    tail = ""
    while n:
        n, r = divmod(n, 62)
        tail = _B62[r] + tail
    return to18(prefix + POD + tail.rjust(9, "0"))


def normalise_id(value: str) -> str | None:
    """A 15- or 18-character id as the 18-character form, or None if it is not a well-formed id."""
    if not isinstance(value, str) or len(value) not in (15, 18) or any(c not in _B62 for c in value):
        return None
    full = to18(value[:15])
    return full if len(value) == 15 or value[:15] + value[15:].upper() == full else None
