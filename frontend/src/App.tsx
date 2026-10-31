import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import HomePage from "./HomePage";
import AuthPage from "./AuthPage";
import "./profile.css";
import "./management.css";
import { authenticatedFetch, supabase, type Session } from "./lib/auth";

type Customer = {
  id: number;
  name: string;
  phone: string;
  amount_due: number | string;
  status?: string | null;
  promise_date?: string | null;
  do_not_call?: boolean;
  next_followup_date?: string | null;
};

type CallRecord = {
  id: number;
  customer_id: number;
  customer_name?: string | null;
  phone?: string | null;
  called_at?: string | null;
  outcome?: string | null;
  promise_date?: string | null;
  notes?: string | null;
  transcript?: string | null;
  summary?: string | null;
  recording_url?: string | null;
  duration_seconds?: number | string | null;
  agent_phone?: string | null;
  bolna_execution_id?: string | null;
  status?: string | null;
};

type DashboardSummary = {
  outstanding: number | string;
  recovered: number | string;
  recovered_after_call: number | string;
  recovery_rate: number | null;
  promised_today: number;
  overdue_promises: { count: number; amount: number | string; max_days: number };
  disputes: number;
  no_answer: number;
  completed: number;
  connected_rate: number | null;
  safety_events: Record<string, number>;
};

type Followup = {
  id: number;
  name: string;
  masked_phone: string;
  amount_due: number | string;
  reason: string;
  last_call_outcome?: string | null;
  last_call_summary?: string | null;
  next_scheduled_call?: string | null;
  status?: string | null;
};

type ShopProfile = {
  name: string;
  type: string;
  location: string;
  language: string;
  calling_hours: string;
  validation_stage: string;
};

type CustomerStatus = {
  label: string;
  className: string;
  filter: "paid" | "promised" | "overdue" | "do_not_call" | "scheduled" | "no_answer" | "disputed";
};

type LoadError = { customers?: string; calls?: string; profile?: string };
type Filter = "all" | "unpaid" | "paid" | "promised";

const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

function formatAmount(value: number | string): string {
  return currency.format(Number(value) || 0);
}

function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T00:00:00`)
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value?: string | null): string {
  const date = parseDate(value);
  return date
    ? new Intl.DateTimeFormat("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(date)
    : "—";
}

function formatDateTime(value?: string | null): string {
  const date = parseDate(value);
  return date
    ? new Intl.DateTimeFormat("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "Asia/Kolkata",
      }).format(date)
    : "Not recorded";
}

function formatDuration(value?: number | string | null): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  const seconds = Math.max(0, Math.round(Number(value) || 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function transcriptTurns(transcript?: string | null): { speaker: string; text: string }[] {
  if (!transcript?.trim()) return [];
  const turns: { speaker: string; text: string }[] = [];
  for (const line of transcript.split(/\r?\n/)) {
    const match = line.match(/^\s*(assistant|agent|user|customer)\s*:\s*(.*)$/i);
    if (match) {
      const speaker = /^(assistant|agent)$/i.test(match[1]) ? "Agent" : "User";
      turns.push({ speaker, text: match[2] });
    } else if (turns.length) {
      turns[turns.length - 1].text += `\n${line}`;
    } else {
      turns.push({ speaker: "Conversation", text: line });
    }
  }
  return turns.filter((turn) => turn.text.trim());
}

function callStatusText(value?: string | null): string {
  if (!value) return "Unknown";
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function initials(name?: string): string {
  return (name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] || "")
    .join("")
    .toUpperCase();
}

function customerStatus(customer: Customer): CustomerStatus {
  const status = (customer.status || "").toLowerCase();
  const promiseDate = parseDate(customer.promise_date || customer.next_followup_date);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (Number(customer.amount_due) <= 0 || /paid|settled|clear/.test(status)) {
    return { label: "Paid", className: "status-paid", filter: "paid" };
  }
  if (customer.do_not_call || status === "do_not_call") {
    return { label: "Do not call", className: "status-overdue", filter: "do_not_call" };
  }
  if (status === "call_scheduled") {
    return { label: "Call scheduled", className: "status-promised", filter: "scheduled" };
  }
  if (status === "no_answer") {
    return { label: "No answer", className: "status-overdue", filter: "no_answer" };
  }
  if (status === "disputed") {
    return { label: "Disputed", className: "status-overdue", filter: "disputed" };
  }
  if (/overdue|late/.test(status) || (promiseDate && promiseDate < today)) {
    return {
      label: "Needs follow-up",
      className: "status-overdue",
      filter: "overdue",
    };
  }
  if (/promis|commit/.test(status) || promiseDate) {
    return {
      label: "Promised",
      className: "status-promised",
      filter: "promised",
    };
  }
  return {
    label: customer.status || "Pending",
    className: "",
    filter: "overdue",
  };
}

async function getJson<T>(path: string): Promise<T> {
  const response = path === "/health"
    ? await fetch(path, { headers: { Accept: "application/json" } })
    : await authenticatedFetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body: { detail?: string } = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status message when the response isn't JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function outcomeText(value?: string | null): string {
  const labels: Record<string, string> = {
    promised: "Payment promised",
    no_money_now: "No money right now",
    disputed: "Amount disputed",
    no_answer: "No answer",
    completed: "Call completed",
    unknown: "Outcome not recorded",
  };
  const key = (value || "unknown").toLowerCase();
  return labels[key] || key.replace(/[_-]/g, " ");
}

function Dashboard({ onSignOut }: { onSignOut: () => void }) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [followups, setFollowups] = useState<Followup[]>([]);
  const [profile, setProfile] = useState<ShopProfile | null>(null);
  const [errors, setErrors] = useState<LoadError>({});
  const [connected, setConnected] = useState<boolean | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<Customer | null>(null);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [customerFormOpen, setCustomerFormOpen] = useState(false);
  const [customerForm, setCustomerForm] = useState({ name: "", phone: "", amount_due: "" });
  const [formError, setFormError] = useState("");
  const [selectedCall, setSelectedCall] = useState<CallRecord | null>(null);
  const [detailsSyncing, setDetailsSyncing] = useState(false);
  const [detailsSyncError, setDetailsSyncError] = useState("");
  const [recordingSource, setRecordingSource] = useState<string | null>(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState("");
  const [calling, setCalling] = useState(false);
  const [callError, setCallError] = useState("");
  const [toast, setToast] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const customerDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const call = selectedCall;
    if (!call?.bolna_execution_id || (call.transcript && call.summary && call.duration_seconds != null && call.recording_url)) {
      setDetailsSyncing(false);
      setDetailsSyncError("");
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    setDetailsSyncing(true);
    setDetailsSyncError("");
    void authenticatedFetch(`/calls/${call.id}/sync`, { method: "POST", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body: { detail?: string } = await response.json().catch(() => ({}));
          throw new Error(body.detail || "Could not refresh details from Bolna.");
        }
        return response.json() as Promise<CallRecord>;
      })
      .then((updatedCall) => {
        if (cancelled) return;
        setSelectedCall(updatedCall);
        setCalls((previous) => previous.map((item) => item.id === updatedCall.id ? updatedCall : item));
      })
      .catch((error: unknown) => {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setDetailsSyncError(error instanceof Error ? error.message : "Could not refresh details from Bolna.");
        }
      })
      .finally(() => {
        if (!cancelled) setDetailsSyncing(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [selectedCall?.id]);

  useEffect(() => {
    if (!selectedCall?.recording_url) {
      setRecordingSource(null);
      setRecordingLoading(false);
      setRecordingError("");
      return;
    }

    const controller = new AbortController();
    let objectUrl: string | null = null;
    let cancelled = false;
    setRecordingSource(null);
    setRecordingLoading(true);
    setRecordingError("");
    void authenticatedFetch(selectedCall.recording_url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Recording is unavailable or has expired.");
        return response.blob();
      })
      .then((audio) => {
        objectUrl = URL.createObjectURL(audio);
        if (!cancelled) setRecordingSource(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch((error: unknown) => {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setRecordingError(error instanceof Error ? error.message : "Could not load the recording.");
        }
      })
      .finally(() => {
        if (!cancelled) setRecordingLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedCall?.id, selectedCall?.recording_url]);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    const [customerResult, callResult, profileResult, healthResult, summaryResult, followupResult] = await Promise.allSettled([
      getJson<Customer[]>("/customers"),
      getJson<CallRecord[]>("/calls"),
      getJson<ShopProfile>("/shop-profile"),
      getJson<{ status: string }>("/health"),
      getJson<DashboardSummary>("/dashboard/summary"),
      getJson<{ items: Followup[] }>("/dashboard/followups?page=1&page_size=25"),
    ]);
    const nextErrors: LoadError = {};

    if (customerResult.status === "fulfilled") {
      setCustomers(Array.isArray(customerResult.value) ? customerResult.value : []);
    } else {
      nextErrors.customers = customerResult.reason.message;
    }
    if (callResult.status === "fulfilled") {
      setCalls(Array.isArray(callResult.value) ? callResult.value : []);
    } else {
      setCalls([]);
      nextErrors.calls = callResult.reason.message;
    }
    if (profileResult.status === "fulfilled") {
      setProfile(profileResult.value);
    } else {
      nextErrors.profile = profileResult.reason.message;
    }
    setConnected(healthResult.status === "fulfilled");
    if (summaryResult.status === "fulfilled") setSummary(summaryResult.value);
    if (followupResult.status === "fulfilled") setFollowups(followupResult.value.items || []);
    setErrors(nextErrors);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (selectedCustomer && !dialog.open) dialog.showModal();
    if (!selectedCustomer && dialog.open) dialog.close();
  }, [selectedCustomer]);

  useEffect(() => {
    const dialog = customerDialogRef.current;
    if (!dialog) return;
    if (customerFormOpen && !dialog.open) dialog.showModal();
    if (!customerFormOpen && dialog.open) dialog.close();
  }, [customerFormOpen]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(""), 3800);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const pendingCustomers = useMemo(
    () => customers.filter((customer) => Number(customer.amount_due) > 0),
    [customers],
  );
  const totalDue = pendingCustomers.reduce(
    (total, customer) => total + (Number(customer.amount_due) || 0),
    0,
  );
  const promiseCount = pendingCustomers.filter(
    (customer) => customerStatus(customer).filter === "promised",
  ).length;
  const kpi = summary || {
    outstanding: totalDue, recovered: 0, recovered_after_call: 0, recovery_rate: null,
    promised_today: promiseCount, overdue_promises: { count: 0, amount: 0, max_days: 0 },
    disputes: 0, no_answer: 0, completed: calls.filter((call) => call.status === "completed").length,
    connected_rate: null, safety_events: {},
  };

  const visibleCustomers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return customers.filter((customer) => {
      const status = customerStatus(customer);
      const matchesFilter =
        filter === "all" ||
        (filter === "promised"
          ? status.filter === "promised"
          : filter === "paid"
            ? status.filter === "paid"
            : filter === "unpaid"
              ? status.filter !== "paid"
              : status.filter === "overdue");
      const matchesQuery = `${customer.name} ${customer.phone} ${customer.id}`
        .toLowerCase()
        .includes(query);
      return matchesFilter && matchesQuery;
    });
  }, [customers, filter, search]);

  function startCall(customer: Customer) {
    setSelectedCustomer(customer);
    setCallError("");
    setCalling(false);
  }

  async function triggerCall() {
    if (!selectedCustomer) return;
    setCalling(true);
    setCallError("");
    try {
      const response = await authenticatedFetch("/calls/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ customer_id: selectedCustomer.id }),
      });
      const result: { detail?: string; message?: string } = await response
        .json()
        .catch(() => ({}));
      if (!response.ok) {
        throw new Error(result.detail || `Could not place the call (${response.status})`);
      }

      setToast(result.message || `Call started for ${selectedCustomer.name}.`);
      setSelectedCustomer(null);
    } catch (error) {
      setCallError(error instanceof Error ? error.message : "Could not place the call.");
      setCalling(false);
    }

  }

  function openCustomerForm(customer?: Customer) {
    setCustomerFormOpen(true);
    setEditingCustomer(customer || null);
    setCustomerForm(customer
      ? { name: customer.name, phone: customer.phone, amount_due: String(customer.amount_due) }
      : { name: "", phone: "", amount_due: "" });
    setFormError("");
  }

  async function saveCustomer(event: FormEvent) {
    event.preventDefault();
    const amount = Number(customerForm.amount_due);
    if (!customerForm.name.trim() || !customerForm.phone.trim() || !Number.isFinite(amount) || amount < 0) {
      setFormError("Enter a name, valid phone number, and non-negative amount.");
      return;
    }
    try {
      const response = await authenticatedFetch(editingCustomer ? `/customers/${editingCustomer.id}` : "/customers", {
        method: editingCustomer ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ name: customerForm.name, phone: customerForm.phone, amount_due: amount }),
      });
      const result: { detail?: string } = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `Could not save customer (${response.status}).`);
      setEditingCustomer(null);
      setCustomerFormOpen(false);
      setCustomerForm({ name: "", phone: "", amount_due: "" });
      setToast(editingCustomer ? "Customer updated." : "Customer added.");
      await loadDashboard();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save customer.");
    }
  }

  async function togglePaid(customer: Customer) {
    const isPaid = customerStatus(customer).filter === "paid";
    if (!window.confirm(isPaid ? `Mark ${customer.name} as unpaid?` : `Mark ${customer.name} as paid?`)) return;
    const response = await authenticatedFetch(`/customers/${customer.id}/${isPaid ? "mark-unpaid" : "mark-paid"}`, { method: "POST" });
    const result: { detail?: string } = await response.json().catch(() => ({}));
    if (!response.ok) {
      setToast(result.detail || "Could not update payment status.");
      return;
    }
    setToast(isPaid ? "Customer marked unpaid." : "Customer marked paid.");
    await loadDashboard();
  }

  async function setCallPreference(customer: Customer, doNotCall: boolean) {
    if (doNotCall && !window.confirm(`Stop follow-up calls for ${customer.name}?`)) return;
    const response = await authenticatedFetch(
      `/customers/${customer.id}/${doNotCall ? "do-not-call" : "allow-calls"}`,
      { method: "POST" },
    );
    const result: { detail?: string } = await response.json().catch(() => ({}));
    if (!response.ok) {
      setToast(result.detail || "Could not update call preference.");
      return;
    }
    setSelectedProfile(null);
    setToast(doNotCall ? "Follow-up calls stopped." : "Follow-up calls allowed.");
    await loadDashboard();
  }

  async function recordPayment(customer: Customer) {
    const value = window.prompt(`Payment received from ${customer.name}`, String(customer.amount_due));
    if (value === null) return;
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) {
      setToast("Enter a payment amount greater than zero.");
      return;
    }
    const response = await authenticatedFetch(`/customers/${customer.id}/payment`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ amount }),
    });
    const result: { detail?: string } = await response.json().catch(() => ({}));
    if (!response.ok) {
      setToast(result.detail || "Could not record payment.");
      return;
    }
    setSelectedProfile(null);
    setToast("Payment recorded.");
    await loadDashboard();
  }

  const todayLabel = new Intl.DateTimeFormat("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());

  return (
    <>
      <div className="announcement">
        <span className="live-dot" /> Your shop, a little more in control
        <span className="announcement-end">A kinder way to follow up&nbsp; ↗</span>
      </div>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Hisaab home">
          <span className="brand-mark">h</span>
          <span>hisaab<span className="brand-period">.</span></span>
        </a>
        <nav className="nav-links" aria-label="Main navigation">
          <a className="nav-active" href="#overview">Overview</a>
          <a href="#customers">Customers</a>
          <a href="#activity">Call activity</a>
        </nav>
        <div className="topbar-right">
          <span className={`connection ${connected === true ? "online" : connected === false ? "offline" : ""}`}>
            <i />
            <span>{connected === true ? "Connected" : connected === false ? "Offline" : "Connecting"}</span>
          </span>
          <button className="avatar" onClick={onSignOut} aria-label="Log out" title="Log out">↗</button>
        </div>
      </header>

      <main id="top">
        <section className="hero" id="overview">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> YOUR DAILY KHATA</div>
            <h1>Good morning.<br /><span>Let’s make follow-ups</span><br />feel a little easier.</h1>
            <p className="hero-subtitle">A clear view of your udhaar, and a polite voice to help bring it home.</p>
            <a className="text-link" href="#customers">See who owes you <span>↓</span></a>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" />
            <div className="hero-center"><span className="hero-center-icon">₹</span><span>YOUR<br />KHATA</span></div>
            <div className="orbit-note note-top"><span className="note-icon">↗</span><span>Gentle reminders<br /><b>in their language</b></span></div>
            <div className="orbit-note note-bottom"><span className="note-icon note-green">✓</span><span>Every promise<br /><b>in one place</b></span></div>
            <span className="orbit-spark spark-one">✳</span><span className="orbit-spark spark-two">✦</span>
          </div>
          <div className="hero-stamp"><span className="stamp-star">✳</span><span>BUILT FOR<br />YOUR SHOP</span></div>
        </section>

        <section className="stats-wrap" aria-label="Khata summary">
          <div className="stats-intro"><span className="section-kicker">AT A GLANCE</span><span className="stats-date">{todayLabel}</span></div>
          <div className="stats-grid">
            <article className="stat-card stat-primary" title="Sum of current amount_due for customers with an unpaid balance."><div className="stat-label">Total outstanding <span className="stat-icon">₹</span></div><div className="stat-value">{loading ? "—" : formatAmount(kpi.outstanding)}</div><div className="stat-caption">Current ledger balance</div><div className="stat-decoration" /></article>
            <article className="stat-card" title="Payments recorded since Monday 00:00 IST."><div className="stat-label">Recovered this week <span className="stat-icon pale">↗</span></div><div className="stat-value">{loading ? "—" : formatAmount(kpi.recovered)}</div><div className="stat-caption">{kpi.recovery_rate == null ? "Rate —" : `Rate ${Math.round(kpi.recovery_rate * 100)}%`}</div></article>
            <article className="stat-card" title="Customers whose promise date is today."><div className="stat-label">Promised today <span className="stat-icon pale">◷</span></div><div className="stat-value">{loading ? "—" : kpi.promised_today}</div><div className="stat-caption">Needs a gentle check-in</div></article>
            <article className="stat-card" title="Customers with a promise date before today, excluding do-not-call customers."><div className="stat-label">Overdue promises <span className="stat-icon pale">!</span></div><div className="stat-value">{loading ? "—" : kpi.overdue_promises.count}</div><div className="stat-caption">{formatAmount(kpi.overdue_promises.amount)} pending</div></article>
            <article className="stat-card" title="Disputed balances needing shopkeeper review."><div className="stat-label">Disputes <span className="stat-icon pale">?</span></div><div className="stat-value">{loading ? "—" : kpi.disputes}</div><div className="stat-caption">Needs your attention</div></article>
            <article className="stat-card" title="Customers whose latest call was not answered."><div className="stat-label">No answer <span className="stat-icon pale">⌁</span></div><div className="stat-value">{loading ? "—" : kpi.no_answer}</div><div className="stat-caption">Retry when appropriate</div></article>
            <article className="stat-card" title="Calls completed since Monday 00:00 IST."><div className="stat-label">Calls completed <span className="stat-icon pale">✓</span></div><div className="stat-value">{loading ? "—" : kpi.completed}</div><div className="stat-caption">{kpi.connected_rate == null ? "Connected rate —" : `Connected ${Math.round(kpi.connected_rate * 100)}%`}</div></article>
          </div>
        </section>

        {profile && <section className="profile-strip section-block" aria-label="Shop profile">
          <div>
            <span className="section-kicker">YOUR SHOP</span>
            <h2>{profile.name}</h2>
            <p className="section-description">{profile.validation_stage}</p>
          </div>
          <div className="profile-details">
            <span><b>Type</b>{profile.type}</span>
            <span><b>Location</b>{profile.location || "Not set"}</span>
            <span><b>Language</b>{profile.language}</span>
            <span><b>Calling hours</b>{profile.calling_hours}</span>
          </div>
        </section>}

        <section className="followups-section section-block" id="followups">
          <div className="section-heading">
            <div><span className="section-kicker">TODAY’S FOLLOW-UPS</span><h2>Who needs a little attention?</h2><p className="section-description">Prioritised from promises, disputes, and recent call outcomes. Do-not-call customers are excluded.</p></div>
            <div className="heading-actions"><a className="button button-secondary" href="#customers">All customers</a></div>
          </div>
          <div className="followup-list">
            {loading ? <div className="activity-loading"><span className="spinner" /> Loading follow-ups…</div> : followups.length ? followups.map((item) => {
              const customer = customers.find((entry) => entry.id === item.id);
              return <article className="followup-row" key={item.id}>
                <div><strong>{item.name}</strong><span>{item.masked_phone} · {item.reason}</span></div>
                <b>{formatAmount(item.amount_due)}</b>
                <span className="muted">{item.last_call_summary || item.last_call_outcome || "No call recorded yet."}</span>
                <div className="row-actions">{customer && <button className="row-action" type="button" onClick={() => startCall(customer)}>Call gently</button>}{customer && <button className="row-action" type="button" onClick={() => void togglePaid(customer)}>Mark paid</button>}</div>
              </article>;
            }) : <div className="empty-state"><strong>No follow-ups for now</strong><span>That’s a good thing. New customers and promises will appear here.</span></div>}
          </div>
        </section>

        <section className="safety-panel section-block">
          <div><span className="section-kicker">RELATIONSHIP SAFETY</span><h2>Collect without pressure.</h2><p className="section-description">Opt-outs and sensitive outcomes stay visible to you, never in the customer’s call.</p></div>
          <div className="safety-grid">{Object.entries(kpi.safety_events).map(([key, value]) => <span key={key}><b>{value}</b>{key.replace(/_/g, " ")}</span>)}</div>
        </section>

        <section className="customers-section section-block" id="customers">
          <div className="section-heading">
            <div><span className="section-kicker">YOUR PEOPLE</span><h2>Customer khata</h2><p className="section-description">Know where things stand. Reach out when you’re ready.</p></div>
            <div className="heading-actions"><button className="button button-primary" onClick={() => openCustomerForm()} type="button">+ Add customer</button><button className={`button button-secondary ${loading ? "refreshing" : ""}`} onClick={() => void loadDashboard()} type="button"><span className="refresh-icon">↻</span> Refresh data</button></div>
          </div>
          <div className="table-toolbar">
            <label className="search-box"><span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} type="search" placeholder="Find a customer..." autoComplete="off" /></label>
            <div className="filter-tabs" role="group" aria-label="Filter customers">
              {(["all", "unpaid", "paid", "promised"] as const).map((value) => <button key={value} className={`filter-tab ${filter === value ? "selected" : ""}`} onClick={() => setFilter(value)} type="button">{value === "all" ? "Everyone" : value === "unpaid" ? "Unpaid" : value === "paid" ? "Paid" : "Promised"}</button>)}
            </div>
          </div>
          <div className="table-shell">
            <table><thead><tr><th>CUSTOMER</th><th>PHONE</th><th>AMOUNT DUE</th><th>STATUS</th><th>PAYMENT DATE</th><th><span className="sr-only">Action</span></th></tr></thead>
              <tbody>
                {loading && !customers.length ? <tr><td colSpan={6} className="loading-cell"><span className="spinner" /> Getting your khata…</td></tr> : visibleCustomers.length ? visibleCustomers.map((customer) => {
                  const status = customerStatus(customer);
                  const hasBalance = Number(customer.amount_due) > 0;
                  return <tr key={customer.id}>
                    <td><button className="customer-cell customer-cell-button" onClick={() => setSelectedProfile(customer)} type="button"><span className="customer-initials">{initials(customer.name)}</span><span><span className="customer-name">{customer.name || "Unnamed customer"}</span><span className="customer-id">Khata #{customer.id}</span></span></button></td>
                    <td>{customer.phone || "—"}</td><td><span className="amount">{formatAmount(customer.amount_due)}</span></td>
                    <td><span className={`status-badge ${status.className}`}>{status.label}</span></td><td className="date-cell">{formatDate(customer.promise_date)}</td>
                    <td><div className="row-actions"><button className="row-action" onClick={() => openCustomerForm(customer)} type="button">Edit</button><button className="row-action" onClick={() => void togglePaid(customer)} type="button">{status.filter === "paid" ? "Unpaid" : "Mark paid"}</button>{hasBalance && !customer.do_not_call && <button className="row-action" onClick={() => startCall(customer)} type="button">Call gently&nbsp; ↗</button>}</div></td>
                  </tr>;
                }) : <tr><td colSpan={6}><div className="empty-state"><strong>{customers.length ? "No customers found" : "Your khata is ready when you are"}</strong><span>{customers.length ? "Try another name or filter." : "Customers will appear here once they are added to your khata."}</span></div></td></tr>}
              </tbody>
            </table>
            <div className="table-footer"><span>Showing {visibleCustomers.length} of {customers.length} customers</span><span>Amounts shown in Indian Rupees</span></div>
          </div>
          {errors.customers && <div className="load-error" role="alert">{errors.customers}</div>}
        </section>

        <section className="care-strip"><div className="care-icon">♡</div><div><span className="section-kicker">A LITTLE CARE GOES A LONG WAY</span><h3>Good relationships are good business.</h3><p>Calls are placed only when you ask, only during shop hours, and never share debt details with anyone else. Every customer can opt out.</p></div><a href="#customers" className="care-link">Choose someone to call <span>↗</span></a></section>

        <section className="activity-section section-block" id="activity">
          <div className="section-heading activity-heading"><div><span className="section-kicker">THE CONVERSATIONS</span><h2>Recent call activity</h2><p className="section-description">Every call and customer promise, together in one place.</p></div><span className="activity-pill"><i /> Latest first</span></div>
          <div className="activity-list">
            {loading && !calls.length ? <div className="activity-loading"><span className="spinner" /> Loading call activity…</div> : calls.length ? calls.map((call) => {
              const outcome = (call.outcome || "unknown").toLowerCase();
              const summary = call.summary || call.notes || "Call saved. No summary was included.";
              return <article className="activity-item activity-clickable" key={call.id} onClick={() => setSelectedCall(call)} onKeyDown={(event) => { if (event.key === "Enter") setSelectedCall(call); }} role="button" tabIndex={0}>
                <span className={`activity-icon ${outcome}`}>{outcome === "promised" ? "✓" : outcome === "disputed" ? "!" : "⌁"}</span>
                <div className="activity-main"><div className="activity-title">{call.customer_name || `Customer #${call.customer_id}`} <span>· {call.phone || ""}</span></div><div className="activity-meta">{formatDate(call.called_at)}{call.promise_date ? ` · Payment promised by ${formatDate(call.promise_date)}` : ""}</div><div className="activity-note">{summary}</div></div>
                <span className={`outcome-label ${outcome}`}>{outcomeText(outcome)}</span>
              </article>;
            }) : <div className="empty-state"><strong>No recorded calls yet</strong><span>After a call finishes, its outcome and customer promise will show up here.</span></div>}
          </div>
          {errors.calls && <div className="load-error" role="alert">{errors.calls}</div>}
        </section>

        <section className="closing-band"><div className="closing-orbit" aria-hidden="true" /><span className="section-kicker">YOUR KHATA, WITH A VOICE</span><h2>One less thing to<br />keep in your head.</h2><p>Pick a customer above to start a thoughtful follow-up.</p><a href="#customers" className="button button-light">View customer khata <span>↑</span></a></section>
      </main>

      <footer className="footer"><a className="brand footer-brand" href="#top"><span className="brand-mark">h</span><span>hisaab<span className="brand-period">.</span></span></a><span>Made for the people who keep the neighborhood running.</span><a href="#top" className="back-top">Back to top ↑</a></footer>

      <dialog className="call-dialog" ref={dialogRef} onClose={() => setSelectedCustomer(null)}>
        <button className="dialog-close" onClick={() => setSelectedCustomer(null)} aria-label="Close" type="button">×</button>
        <div className="dialog-mark">⌁</div><span className="section-kicker">A THOUGHTFUL FOLLOW-UP</span>
        <h2>Call <span>{selectedCustomer?.name || "this customer"}</span>?</h2>
        <p>Hisaab will place a polite call in Hindi or Hinglish to remind them about their balance.</p>
        <div className="dialog-detail"><span>Amount due</span><b>{selectedCustomer ? formatAmount(selectedCustomer.amount_due) : "—"}</b></div>
        <div className="dialog-actions"><button className="button button-secondary" onClick={() => setSelectedCustomer(null)} type="button">Not now</button><button className="button button-call" disabled={calling} onClick={() => void triggerCall()} type="button">{calling ? "Connecting…" : "Place call ↗"}</button></div>
        {callError && <p className="dialog-error" role="alert">{callError}</p>}
      </dialog>
      <dialog className="call-dialog customer-form-dialog" ref={customerDialogRef} onClose={() => { setEditingCustomer(null); setCustomerFormOpen(false); setCustomerForm({ name: "", phone: "", amount_due: "" }); }}>
        <button className="dialog-close" onClick={() => setCustomerFormOpen(false)} aria-label="Close" type="button">×</button>
        <span className="section-kicker">{editingCustomer ? "EDIT CUSTOMER" : "ADD CUSTOMER"}</span>
        <h2>{editingCustomer ? "Update khata" : "Add someone to your khata"}</h2>
        <form onSubmit={(event) => void saveCustomer(event)} className="customer-form">
          <label>Name<input value={customerForm.name} onChange={(event) => setCustomerForm({ ...customerForm, name: event.target.value })} /></label>
          <label>Phone<input value={customerForm.phone} onChange={(event) => setCustomerForm({ ...customerForm, phone: event.target.value })} placeholder="+91 98765 43210" /></label>
          <label>Amount due<input value={customerForm.amount_due} onChange={(event) => setCustomerForm({ ...customerForm, amount_due: event.target.value })} type="number" min="0" step="0.01" /></label>
          {formError && <p className="dialog-error" role="alert">{formError}</p>}
          <div className="dialog-actions"><button className="button button-secondary" onClick={() => setCustomerFormOpen(false)} type="button">Cancel</button><button className="button button-call" type="submit">Save customer</button></div>
        </form>
      </dialog>
      {selectedCall && <div className="detail-backdrop" role="presentation" onClick={() => setSelectedCall(null)}><section className="call-detail" role="dialog" aria-modal="true" aria-label="Call details" onClick={(event) => event.stopPropagation()}>
        <button className="dialog-close" onClick={() => setSelectedCall(null)} aria-label="Close" type="button">×</button>
        <span className="section-kicker">CALL DETAILS</span><h2>{selectedCall.customer_name || `Customer #${selectedCall.customer_id}`}</h2>
        <p className="activity-meta">{formatDateTime(selectedCall.called_at)} · {formatDuration(selectedCall.duration_seconds)} · {callStatusText(selectedCall.status)}</p>
        {detailsSyncing && <p className="muted" role="status">Refreshing details from Bolna…</p>}
        {detailsSyncError && <p className="muted" role="status">{detailsSyncError}</p>}
        <dl className="call-detail-grid">
          <div><dt>Customer phone</dt><dd>{selectedCall.phone || "Not recorded"}</dd></div>
          <div><dt>Agent phone</dt><dd>{selectedCall.agent_phone || "Not recorded"}</dd></div>
          <div><dt>Outcome</dt><dd>{outcomeText(selectedCall.outcome)}</dd></div>
          <div><dt>Promise date</dt><dd>{formatDate(selectedCall.promise_date)}</dd></div>
          <div className="call-summary-field"><dt>Summary</dt><dd>{selectedCall.summary || selectedCall.notes || "Not available yet."}</dd></div>
        </dl>
        <h3>Transcript</h3>
        {selectedCall.transcript ? <div className="transcript-turns">{transcriptTurns(selectedCall.transcript).map((turn, index) => <p className="transcript-turn" key={`${index}-${turn.speaker}`}><strong>{turn.speaker}</strong><span>{turn.text}</span></p>)}</div> : <p className="muted">Transcript not available yet.</p>}
        <h3>Recording</h3>{recordingLoading ? <p className="muted">Loading recording…</p> : recordingError ? <p className="muted" role="status">{recordingError}</p> : recordingSource ? <audio controls preload="none" src={recordingSource} /> : <p className="muted">Recording not available yet.</p>}
      </section></div>}
      {selectedProfile && <div className="detail-backdrop" role="presentation" onClick={() => setSelectedProfile(null)}><section className="call-detail customer-profile-detail" role="dialog" aria-modal="true" aria-label="Customer details" onClick={(event) => event.stopPropagation()}>
        <button className="dialog-close" onClick={() => setSelectedProfile(null)} aria-label="Close" type="button">×</button>
        <span className="section-kicker">CUSTOMER PROFILE</span>
        <h2>{selectedProfile.name}</h2>
        <p className="activity-meta">Khata #{selectedProfile.id} · {selectedProfile.phone}</p>
        <dl className="call-detail-grid">
          <div><dt>Amount due</dt><dd>{formatAmount(selectedProfile.amount_due)}</dd></div>
          <div><dt>Status</dt><dd>{customerStatus(selectedProfile).label}</dd></div>
          <div><dt>Promise date</dt><dd>{formatDate(selectedProfile.promise_date)}</dd></div>
          <div><dt>Next step</dt><dd>{selectedProfile.do_not_call ? "Do not call" : selectedProfile.next_followup_date ? `Follow up on ${formatDate(selectedProfile.next_followup_date)}` : Number(selectedProfile.amount_due) > 0 ? "Follow up when ready" : "No follow-up needed"}</dd></div>
        </dl>
        <div className="dialog-actions profile-detail-actions">
          <button className="button button-secondary" onClick={() => { setSelectedProfile(null); openCustomerForm(selectedProfile); }} type="button">Edit customer</button>
          {Number(selectedProfile.amount_due) > 0 && <button className="button button-call" onClick={() => { setSelectedProfile(null); startCall(selectedProfile); }} type="button">Call gently ↗</button>}
        </div>
        <div className="dialog-actions profile-detail-actions">
        <button className="button button-secondary" onClick={() => void setCallPreference(selectedProfile, !selectedProfile.do_not_call)} type="button">{selectedProfile.do_not_call ? "Allow calls" : "Do not call"}</button>
        {Number(selectedProfile.amount_due) > 0 && <button className="button button-secondary" onClick={() => void recordPayment(selectedProfile)} type="button">Record payment</button>}
        </div>
      </section></div>}
      <div className={`toast ${toast ? "visible" : ""}`} role="status" aria-live="polite">{toast}</div>
    </>
  );
}

type Route = "home" | "dashboard" | "login" | "signup" | "customer-login";

function routeFromHash(): Route {
  const path = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  if (path === "dashboard") return "dashboard";
  if (path === "login") return "login";
  if (path === "signup") return "signup";
  if (path === "customer-login") return "customer-login";
  return "home";
}

function App() {
  const [route, setRoute] = useState<Route>(routeFromHash);
  const [session, setSession] = useState<Session | null>(null);
  const [demoToken, setDemoToken] = useState(() => sessionStorage.getItem("hisaab_demo_token"));
  const [authReady, setAuthReady] = useState(!supabase);

  useEffect(() => {
    const updateRoute = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  useEffect(() => {
    if (!supabase) {
      setAuthReady(true);
      return;
    }
    let mounted = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session);
        setAuthReady(true);
      }
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setAuthReady(true);
    });
    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  const navigate = (path: string) => { window.location.hash = `/${path}`; };
  const onAuthenticated = () => {
    setDemoToken(sessionStorage.getItem("hisaab_demo_token"));
    setRoute("dashboard");
    window.location.hash = "/dashboard";
  };
  if (route === "dashboard") {
    if (!authReady) return <main className="auth-loading">Checking your session…</main>;
    if (!session && !demoToken) return <AuthPage page="login" onAuthenticated={onAuthenticated} />;
    return <Dashboard onSignOut={() => { sessionStorage.removeItem("hisaab_demo_token"); setDemoToken(null); void supabase?.auth.signOut(); window.location.hash = "/"; }} />;
  }
  if (route === "login" || route === "signup" || route === "customer-login") {
    return <AuthPage page={route} onAuthenticated={onAuthenticated} />;
  }
  return <HomePage navigate={navigate} />;
}

export default App;
