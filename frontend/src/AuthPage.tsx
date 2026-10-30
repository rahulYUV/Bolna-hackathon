import { useState, type FormEvent } from "react";
import { authenticatedFetch, supabase } from "./lib/auth";
import "./auth.css";

type AuthPageProps = {
  page: "login" | "signup" | "customer-login";
  onAuthenticated: () => void;
};

function toE164(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length === 10) return `+91${digits}`;
  return `+${digits}`;
}

function AuthPage({ page, onAuthenticated }: AuthPageProps) {
  const [phoneInput, setPhoneInput] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const isDemoOnlyPage = page !== "login";

  async function requestCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const phone = toE164(phoneInput);
    if (!/^\+\d{10,15}$/.test(phone)) {
      setError("Enter a valid mobile number with country code.");
      return;
    }
    setWorking(true);
    try {
      const allowResponse = await fetch("/auth/check-shopkeeper-phone", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ phone }),
      });
      if (!allowResponse.ok) {
        const body: { detail?: string } = await allowResponse.json().catch(() => ({}));
        throw new Error(body.detail || "This number is not enabled for the shopkeeper demo.");
      }

      const modeResponse = await fetch("/auth/demo-mode");
      const mode: { enabled?: boolean } = await modeResponse.json().catch(() => ({}));
      if (mode.enabled) {
        setDemoMode(true);
        setOtpSent(true);
        setMessage("Local demo mode is on. Enter any six digits to continue.");
        return;
      }

      if (!supabase) {
        throw new Error("Supabase Auth is not configured. Add its project URL and public key to the environment first.");
      }

      const { error: authError } = await supabase.auth.signInWithOtp({
        phone,
        options: { shouldCreateUser: true },
      });
      if (authError) throw authError;
      setOtpSent(true);
      setMessage(`A sign-in code was sent to ${phone}.`);
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Could not send a sign-in code.");
    } finally {
      setWorking(false);
    }
  }

  async function verifyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking(true);
    setError("");
    try {
      const phone = toE164(phoneInput);
      if (demoMode) {
        const demoResponse = await fetch("/auth/demo-login", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ phone, otp: otp.trim() }),
        });
        const demoResult: { access_token?: string; detail?: string } = await demoResponse.json().catch(() => ({}));
        if (!demoResponse.ok || !demoResult.access_token) {
          throw new Error(demoResult.detail || "Demo login was rejected.");
        }
        sessionStorage.setItem("hisaab_demo_token", demoResult.access_token);
        const response = await authenticatedFetch("/auth/session");
        if (!response.ok) {
          sessionStorage.removeItem("hisaab_demo_token");
          const body: { detail?: string } = await response.json().catch(() => ({}));
          throw new Error(body.detail || "This account is not enabled for the shopkeeper demo.");
        }
        onAuthenticated();
        return;
      }

      if (!supabase) throw new Error("Supabase Auth is not configured.");
      const { error: verifyError } = await supabase.auth.verifyOtp({
        phone,
        token: otp.trim(),
        type: "sms",
      });
      if (verifyError) throw verifyError;

      const response = await authenticatedFetch("/auth/session");
      if (!response.ok) {
        const body: { detail?: string } = await response.json().catch(() => ({}));
        await supabase.auth.signOut();
        throw new Error(body.detail || "This account is not enabled for the shopkeeper demo.");
      }
      onAuthenticated();
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "That code could not be verified.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="auth-shell">
      <a className="brand auth-brand" href="#/" aria-label="Back to Hisaab home"><span className="brand-mark">h</span><span>hisaab<span className="brand-period">.</span></span></a>
      <section className="auth-card">
        <div className="auth-symbol">{isDemoOnlyPage ? "♡" : "↗"}</div>
        <span className="section-kicker">{isDemoOnlyPage ? "SHOPKEEPER DEMO" : "SHOPKEEPER LOGIN"}</span>
        <h1>{isDemoOnlyPage ? "One shop, one owner." : otpSent ? "Check your phone." : "Welcome back."}</h1>
        <p className="auth-intro">{isDemoOnlyPage ? "This demo currently has one shopkeeper account. Customer accounts and public sign-up are turned off." : otpSent ? "Enter the 6-digit code to open your shop dashboard." : "Log in with the owner’s registered mobile number. We’ll send a one-time code."}</p>

        {isDemoOnlyPage ? (
          <div className="auth-notice"><span>ⓘ</span><span>For now, customer sign-in and account creation are disabled. <a href="#/login">Continue to shopkeeper login</a>.</span></div>
        ) : !otpSent ? (
          <form onSubmit={requestCode}>
            <label>Owner mobile number<div className="phone-field"><span>+91</span><input name="phone" type="tel" inputMode="tel" value={phoneInput} onChange={(event) => setPhoneInput(event.target.value)} placeholder="10-digit mobile number" autoComplete="tel-national" required /></div></label>
            <button className="button auth-submit" disabled={working} type="submit">{working ? "Sending code…" : "Send sign-in code"} <span>↗</span></button>
          </form>
        ) : (
          <form onSubmit={verifyCode}>
            <label>6-digit verification code<input name="otp" type="text" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="Enter code" autoComplete="one-time-code" required /></label>
            <button className="button auth-submit" disabled={working || otp.length !== 6} type="submit">{working ? "Verifying…" : "Verify and log in"} <span>↗</span></button>
            <button className="auth-resend" disabled={working} onClick={() => { setOtpSent(false); setOtp(""); setMessage(""); }} type="button">Use another number or resend code</button>
          </form>
        )}

        {message && <p className="auth-success" role="status">{message}</p>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        {!isDemoOnlyPage && <div className="auth-notice"><span>ⓘ</span><span>Only the owner number configured for this demo can access customer balances and trigger calls.</span></div>}
      </section>
      <a className="auth-back" href="#/">← Back to Hisaab home</a>
    </main>
  );
}

export default AuthPage;
