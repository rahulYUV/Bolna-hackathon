import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import HomePage from "./HomePage";
import AuthPage from "./AuthPage";
import { authenticatedFetch, supabase, type Session } from "./lib/auth";

type Customer = {
  id: number;
  name: string;
  phone: string;
  amount_due: number | string;
  status?: string | null;
  promise_date?: string | null;
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
};

type CustomerStatus = {
  label: string;
  className: string;
  filter: "paid" | "promised" | "overdue";
};

type LoadError = { customers?: string; calls?: string };
type Filter = "all" | "overdue" | "promised";

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
  const promiseDate = parseDate(customer.promise_date);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (Number(customer.amount_due) <= 0 || /paid|settled|clear/.test(status)) {
    return { label: "Paid", className: "status-paid", filter: "paid" };
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
  const [errors, setErrors] = useState<LoadError>({});
  const [connected, setConnected] = useState<boolean | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [calling, setCalling] = useState(false);
  const [callError, setCallError] = useState("");
  const [toast, setToast] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    const [customerResult, callResult, healthResult] = await Promise.allSettled([
      getJson<Customer[]>("/customers"),
      getJson<CallRecord[]>("/calls"),
      getJson<{ status: string }>("/health"),
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
    setConnected(healthResult.status === "fulfilled");
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

  const visibleCustomers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return customers.filter((customer) => {
      const status = customerStatus(customer);
      const matchesFilter =
        filter === "all" ||
        (filter === "promised"
          ? status.filter === "promised"
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
            <article className="stat-card stat-primary"><div className="stat-label">Total udhaar pending <span className="stat-icon">₹</span></div><div className="stat-value">{loading ? "—" : formatAmount(totalDue)}</div><div className="stat-caption">Across your customer khata</div><div className="stat-decoration" /></article>
            <article className="stat-card"><div className="stat-label">Customers with balance <span className="stat-icon pale">♙</span></div><div className="stat-value">{loading ? "—" : pendingCustomers.length}</div><div className="stat-caption">People in your khata</div></article>
            <article className="stat-card"><div className="stat-label">Promises to follow up <span className="stat-icon pale">◷</span></div><div className="stat-value">{loading ? "—" : promiseCount}</div><div className="stat-caption">Customers with a payment date</div></article>
            <article className="stat-card"><div className="stat-label">Calls made <span className="stat-icon pale">⌁</span></div><div className="stat-value">{loading && !calls.length ? "—" : calls.length}</div><div className="stat-caption">Recorded conversations</div></article>
          </div>
        </section>

        <section className="customers-section section-block" id="customers">
          <div className="section-heading">
            <div><span className="section-kicker">YOUR PEOPLE</span><h2>Customer khata</h2><p className="section-description">Know where things stand. Reach out when you’re ready.</p></div>
            <button className={`button button-secondary ${loading ? "refreshing" : ""}`} onClick={() => void loadDashboard()} type="button"><span className="refresh-icon">↻</span> Refresh data</button>
          </div>
          <div className="table-toolbar">
            <label className="search-box"><span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} type="search" placeholder="Find a customer..." autoComplete="off" /></label>
            <div className="filter-tabs" role="group" aria-label="Filter customers">
              {(["all", "overdue", "promised"] as const).map((value) => <button key={value} className={`filter-tab ${filter === value ? "selected" : ""}`} onClick={() => setFilter(value)} type="button">{value === "all" ? "Everyone" : value === "overdue" ? "Needs follow-up" : "Promised"}</button>)}
            </div>
          </div>
          <div className="table-shell">
            <table><thead><tr><th>CUSTOMER</th><th>PHONE</th><th>AMOUNT DUE</th><th>STATUS</th><th>PAYMENT DATE</th><th><span className="sr-only">Action</span></th></tr></thead>
              <tbody>
                {loading && !customers.length ? <tr><td colSpan={6} className="loading-cell"><span className="spinner" /> Getting your khata…</td></tr> : visibleCustomers.length ? visibleCustomers.map((customer) => {
                  const status = customerStatus(customer);
                  const hasBalance = Number(customer.amount_due) > 0;
                  return <tr key={customer.id}>
                    <td><div className="customer-cell"><span className="customer-initials">{initials(customer.name)}</span><span><span className="customer-name">{customer.name || "Unnamed customer"}</span><span className="customer-id">Khata #{customer.id}</span></span></div></td>
                    <td>{customer.phone || "—"}</td><td><span className="amount">{formatAmount(customer.amount_due)}</span></td>
                    <td><span className={`status-badge ${status.className}`}>{status.label}</span></td><td className="date-cell">{formatDate(customer.promise_date)}</td>
                    <td>{hasBalance ? <button className="row-action" onClick={() => startCall(customer)} type="button">Call gently&nbsp; ↗</button> : <span className="status-badge status-paid">All clear</span>}</td>
                  </tr>;
                }) : <tr><td colSpan={6}><div className="empty-state"><strong>{customers.length ? "No customers found" : "Your khata is ready when you are"}</strong><span>{customers.length ? "Try another name or filter." : "Customers will appear here once they are added to your khata."}</span></div></td></tr>}
              </tbody>
            </table>
            <div className="table-footer"><span>Showing {visibleCustomers.length} of {customers.length} customers</span><span>Amounts shown in Indian Rupees</span></div>
          </div>
          {errors.customers && <div className="load-error" role="alert">{errors.customers}</div>}
        </section>

        <section className="care-strip"><div className="care-icon">♡</div><div><span className="section-kicker">A LITTLE CARE GOES A LONG WAY</span><h3>Good relationships are good business.</h3><p>Calls are placed only when you ask. Your voice agent keeps it polite, private, and in Hindi or Hinglish.</p></div><a href="#customers" className="care-link">Choose someone to call <span>↗</span></a></section>

        <section className="activity-section section-block" id="activity">
          <div className="section-heading activity-heading"><div><span className="section-kicker">THE CONVERSATIONS</span><h2>Recent call activity</h2><p className="section-description">Every call and customer promise, together in one place.</p></div><span className="activity-pill"><i /> Latest first</span></div>
          <div className="activity-list">
            {loading && !calls.length ? <div className="activity-loading"><span className="spinner" /> Loading call activity…</div> : calls.length ? calls.map((call) => {
              const outcome = (call.outcome || "unknown").toLowerCase();
              const summary = call.notes || call.transcript || "Call saved. No transcript or notes were included.";
              return <article className="activity-item" key={call.id}>
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
