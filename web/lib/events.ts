import { supabase } from "./supabaseClient";

export interface ActivityEvent {
  id: number; resource_type: string; resource_id: string; event_type: string;
  payload: Record<string, unknown>; trace_id: string; correlation_id: string | null; created_at: string;
}

const API_BASE = process.env.NODE_ENV === "development" ? "/api" : process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export function streamEvents(options: {
  resourceType?: string; resourceId?: string; onEvent: (event: ActivityEvent) => void;
  onConnection?: (connected: boolean) => void;
}) {
  const controller = new AbortController(); let cursor = 0; let retry = 1000;
  async function connect() {
    while (!controller.signal.aborted) {
      try {
        const { data } = await supabase.auth.getSession();
        const query = new URLSearchParams({ after: String(cursor) });
        if (options.resourceType) query.set("resource_type", options.resourceType);
        if (options.resourceId) query.set("resource_id", options.resourceId);
        const response = await fetch(`${API_BASE}/events/stream?${query}`, { signal: controller.signal,
          headers: data.session?.access_token ? { Authorization: `Bearer ${data.session.access_token}`, "Last-Event-ID": String(cursor) } : {} });
        if (!response.ok || !response.body) throw new Error(`Event stream returned ${response.status}`);
        options.onConnection?.(true); retry = 1000;
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read(); if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n"); buffer = frames.pop() || "";
          for (const frame of frames) {
            if (!frame || frame.startsWith(":")) continue;
            const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
            if (!dataLine) continue;
            const event = JSON.parse(dataLine.slice(6)) as ActivityEvent;
            if (event.id <= cursor) continue;
            cursor = event.id; options.onEvent(event);
          }
        }
      } catch (error) {
        if (controller.signal.aborted) break;
        options.onConnection?.(false);
      }
      await new Promise((resolve) => setTimeout(resolve, retry)); retry = Math.min(retry * 2, 15000);
    }
  }
  void connect(); return () => controller.abort();
}
