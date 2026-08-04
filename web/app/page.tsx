"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

export default function HomePage() {
  const router = useRouter();
  const authDisabled = process.env.NEXT_PUBLIC_DISABLE_AUTH === "true";

  useEffect(() => {
    if (authDisabled) {
      router.replace("/agents");
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      router.replace(data.session ? "/agents" : "/login");
    });
  }, [authDisabled, router]);

  return <p className="page-loading">Loading…</p>;
}
