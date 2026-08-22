"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** An escalated result is ROUTED from inside the tool, in
  the same call that produced it. An agent surface that only returned the flag would be a third
  place an escalation can quietly stop, after the API and the CLI.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with
  no ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..assembly import build_assessment_service
from ..config import Container, Settings, build_container
from ..domain.models import Declaration, DeclarationKind, Instrument
from ..domain.pii import PII_PATTERNS

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "conflicts-gifts-pad-register-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result is not an API response. The API returns to the authenticated caller the text
    that caller just submitted; a TOOL result goes into a model's context, and P-04 says
    minimise the data that reaches a model. The evidence snippet a caller may legitimately read
    back is therefore masked here, on the way to the agent, using the same pattern pack the
    audit write masks with. Walking the whole structure rather than three named fields means a
    future field cannot arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def assess_declaration(
    declaration_id: str,
    employee: str,
    employee_role: str,
    market: str,
    kind: str,
    description: str,
    as_of: str,
    tenant: str,
    counterparty: str = "",
    amount_minor: int = 0,
    currency: str = "",
    symbol: str = "",
    actor: str = DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Screen one declaration and route it for human review when it is flagged.

    The deterministic engine decides which rules fired, the CLEAR / FLAGGED outcome and the
    severity; the model only narrates. When the declaration is flagged, the assessment is
    submitted to the human-review console (rule R8).

    Args:
      declaration_id: The register id for this declaration.
      employee: The employee the declaration is about.
      employee_role: The employee's role (drives the gift threshold).
      market: The market the employee trades in (drives the threshold).
      kind: One of gift, entertainment, outside_interest, political_donation,
        personal_account_deal.
      description: The free-text declaration text.
      as_of: The effective date the reference snapshot is replayed at (YYYY-MM-DD).
      tenant: The tenant partition this record belongs to. REQUIRED, and it has no default:
        defaulting it to the empty string files an untagged record, and the API's read guard
        treats an untagged record as readable by every tenant. The register store refuses an
        untagged record, so an empty value is an error here rather than a silently unowned
        row.
      counterparty: The structured counterparty name, if known.
      amount_minor: The gift/entertainment amount in minor units (cents).
      currency: The amount's currency.
      symbol: The instrument symbol for a personal-account deal.
      actor: The verified identity this call is attributed to.

    Returns:
      A JSON-safe result dict with every string masked for personal data (P-04: a tool result
      goes into a model's context), plus ``review_ref``: where the escalation WENT. It is empty
      only when the assessment did not escalate.
    """
    container = _container(settings)
    service = build_assessment_service(container)
    declaration = Declaration(
        id=declaration_id,
        tenant=tenant,
        employee=employee,
        employee_role=employee_role,
        market=market,
        kind=DeclarationKind(kind),
        description=description,
        as_of=as_of,
        counterparty=counterparty,
        amount_minor=amount_minor,
        currency=currency,
        instrument=Instrument(symbol=symbol) if symbol else None,
    )
    result = service.assess(declaration, actor=actor)
    container.register_store.put(result)
    review_ref = ""
    if result.requires_human_review:
        review_ref = container.review_router.route(result, maker=actor, tenant=tenant)
    payload = _redacted(to_jsonable(result))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("an assessment must serialise to a JSON object")
    # Attached after the redaction pass: it is a routing reference, not narrative text.
    payload["review_ref"] = review_ref
    return payload


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well. Without an anchor a truncation cannot be detected, and the detail
      says so rather than implying a stronger guarantee than the store provides.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (assess_declaration, verify_audit_trail)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path).

    The import is deliberately here rather than at module scope: without it this module, the
    card and every tool would need an agent runtime installed to be imported at all, and the
    offline gate installs none.
    """
    # No ignore comment: the missing-import error for this module is already reported (and
    # ignored) at the TYPE_CHECKING import above, and a second one would be flagged as unused.
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
