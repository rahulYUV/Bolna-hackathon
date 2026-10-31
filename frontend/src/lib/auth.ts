import { createClient, type Session } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabasePublicKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase = supabaseUrl && supabasePublicKey
  ? createClient(supabaseUrl, supabasePublicKey, {
      auth: { autoRefreshToken: true, persistSession: true, detectSessionInUrl: true },
    })
  : null;

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  let accessToken = sessionStorage.getItem("hisaab_demo_token");
  if (!accessToken) {
    if (!supabase) {
      throw new Error("Supabase Auth is not configured. Add the VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY settings.");
    }
    const { data: { session } } = await supabase.auth.getSession();
    accessToken = session?.access_token ?? null;
  }
  if (!accessToken) throw new Error("Please log in to continue.");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401 && sessionStorage.getItem("hisaab_demo_token")) {
    sessionStorage.removeItem("hisaab_demo_token");
    window.location.hash = "/login";
  }
  return response;
}

export type { Session };
