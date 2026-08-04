"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabaseClient";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const authDisabled = process.env.NEXT_PUBLIC_DISABLE_AUTH === "true";
  const router = useRouter();
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    if (authDisabled) {
      setSession(null);
      return;
    }
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => listener.subscription.unsubscribe();
  }, [authDisabled]);

  useEffect(() => {
    if (!authDisabled && session === null) router.replace("/login");
  }, [authDisabled, session, router]);

  if (authDisabled) return <>{children}</>;

  if (session === undefined) return <p className="page-loading">Loading…</p>;
  if (session === null) return null;
  return <>{children}</>;
}
