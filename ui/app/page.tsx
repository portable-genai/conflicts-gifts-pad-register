"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

// What happened to the human-review hand-off, in the words the user needs. A result that
// escalated but is not queued must say so rather than read as reviewed.
const REVIEW_ROUTING_TEXT: Record<string, string> = {
  routed: "Sent to the review console.",
  failed: "Could not reach the review console; this declaration is not queued for review.",
  off: "Review routing is off in this deployment; this declaration is not queued for review.",
};

function reviewRoutingOf(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { review_routing?: unknown };
    return typeof parsed.review_routing === "string" ? parsed.review_routing : undefined;
  } catch {
    return undefined;
  }
}

// The declaration kinds the register screens, as `DeclarationKind` in domain/models.py spells
// them on the wire. An unlisted value is not a kind the API accepts, so the form offers only these.
const KINDS: { value: string; label: string }[] = [
  { value: "gift", label: "Gift" },
  { value: "entertainment", label: "Entertainment" },
  { value: "outside_interest", label: "Outside interest" },
  { value: "political_donation", label: "Political donation" },
  { value: "personal_account_deal", label: "Personal-account deal" },
];

// The kind that names an instrument; the restricted, blackout and MNPI rules screen its symbol.
const PAD_KIND = "personal_account_deal";

interface CardSummary {
  name?: string;
  description?: string;
  skills?: { id: string; name: string }[];
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[0]);
  // A fictional declaration the local profile screens as-is: a trader's SGD 250.00 gift in SG,
  // over the configured SGD 100.00 threshold, so it escalates and routes for human review.
  const [id, setId] = useState("dec-console-0001");
  const [employee, setEmployee] = useState("tan.trader@bank.example");
  const [employeeRole, setEmployeeRole] = useState("trader");
  const [market, setMarket] = useState("SG");
  const [kind, setKind] = useState("gift");
  const [description, setDescription] = useState(
    "Dinner voucher received from Vega Supplies (FICTIONAL) after a deal closed.",
  );
  const [asOf, setAsOf] = useState("2026-08-08");
  const [counterparty, setCounterparty] = useState("Vega Supplies (FICTIONAL)");
  const [amountMinor, setAmountMinor] = useState("25000");
  const [currency, setCurrency] = useState("SGD");
  const [symbol, setSymbol] = useState("FICT");
  const [instrumentName, setInstrumentName] = useState("Fictus Holdings (FICTIONAL)");
  const [isin, setIsin] = useState("");
  const [result, setResult] = useState("");
  const [registerEntry, setRegisterEntry] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<CardSummary | null>(null);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  // A result belongs to the persona that asked for it, so switching persona clears it.
  useEffect(() => {
    setResult("");
    setRegisterEntry("");
  }, [persona]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailed(false);
    setRegisterEntry("");
    const headers = { "Content-Type": "application/json", "X-Dev-Persona": persona };
    try {
      // The tenant and the actor are the verified principal's, so the body carries neither.
      const response = await fetch(API + "/v1/assess", {
        method: "POST",
        headers,
        body: JSON.stringify({
          id,
          employee,
          employee_role: employeeRole,
          market,
          kind,
          description,
          as_of: asOf,
          counterparty,
          amount_minor: Number.parseInt(amountMinor, 10) || 0,
          currency,
          instrument:
            kind === PAD_KIND && symbol.trim() ? { symbol, name: instrumentName, isin } : null,
        }),
      });
      const body = await response.text();
      setFailed(!response.ok);
      setResult(body);
      if (!response.ok) return;
      // Read the entry back from the tenant-scoped register, which is what a reviewer sees.
      const stored = await fetch(API + "/v1/register/" + encodeURIComponent(id), {
        cache: "no-store",
        headers: { "X-Dev-Persona": persona },
      });
      setRegisterEntry(
        stored.ok ? await stored.text() : stored.status + " " + (await stored.text()),
      );
    } catch (error) {
      setFailed(true);
      setResult(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>{card?.name ?? "Agent console"}</h1>
      <p className="sub">
        {card?.description ??
          "Screen a declaration. The verdict is deterministic, cited, and routed to a human reviewer when it escalates."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona (local profile only; the server resolves identity, not this field)
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The declaration</legend>
          <label>
            Declaration id
            <input value={id} onChange={(event) => setId(event.target.value)} />
          </label>
          <label>
            Kind
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              {KINDS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Employee
            <input value={employee} onChange={(event) => setEmployee(event.target.value)} />
          </label>
          <label>
            Employee role
            <input value={employeeRole} onChange={(event) => setEmployeeRole(event.target.value)} />
          </label>
          <label>
            Market
            <input value={market} onChange={(event) => setMarket(event.target.value)} />
          </label>
          <label>
            Effective date (as of, YYYY-MM-DD)
            <input value={asOf} onChange={(event) => setAsOf(event.target.value)} />
          </label>
          <label>
            Counterparty
            <input value={counterparty} onChange={(event) => setCounterparty(event.target.value)} />
          </label>
          <label>
            Amount in minor units (cents)
            <input
              inputMode="numeric"
              value={amountMinor}
              onChange={(event) => setAmountMinor(event.target.value)}
            />
          </label>
          <label>
            Currency
            <input value={currency} onChange={(event) => setCurrency(event.target.value)} />
          </label>
          {kind === PAD_KIND ? (
            <>
              <label>
                Instrument symbol
                <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
              </label>
              <label>
                Instrument name
                <input
                  value={instrumentName}
                  onChange={(event) => setInstrumentName(event.target.value)}
                />
              </label>
              <label>
                Instrument ISIN
                <input value={isin} onChange={(event) => setIsin(event.target.value)} />
              </label>
            </>
          ) : null}
          <label>
            Description
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Working" : "Screen this declaration"}
          </button>
        </fieldset>
      </form>

      {result && REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""] ? (
        <p className="sub" data-review-routing={reviewRoutingOf(result)}>
          {REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""]}
        </p>
      ) : null}
      {result ? <pre className={failed ? "result error" : "result"}>{result}</pre> : null}
      {registerEntry ? (
        <>
          <p className="sub">Register entry, read back from GET /v1/register/{id}:</p>
          <pre className="result">{registerEntry}</pre>
        </>
      ) : null}

      <footer>
        Synthetic, obviously fictional data only. Identity is resolved server-side and the
        client-asserted actor is discarded; see ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}
