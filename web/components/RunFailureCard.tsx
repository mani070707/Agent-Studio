import type { RunFailure } from "@/lib/types";

export default function RunFailureCard({ failure, partial }: {
  failure: RunFailure;
  partial?: Record<string, unknown> | null;
}) {
  const metrics = Object.entries(failure.consumed).filter(([, value]) => value !== 0);
  return (
    <div className="failure-card" role="alert">
      <span className="status-badge danger">{failure.code.replaceAll("_", " ")}</span>
      <h3>{failure.reason}</h3>
      <p>{failure.retryable ? "This failure may succeed when retried later." : "Retrying unchanged is unlikely to help."}</p>
      {failure.retry_after && <p>Provider retry guidance: {failure.retry_after}</p>}
      {metrics.length > 0 && <div className="failure-budget">
        {metrics.map(([name, value]) => <span key={name}><strong>{value}</strong> {name.replaceAll("_", " ")}</span>)}
      </div>}
      <h4>Recommended actions</h4>
      <ul>{failure.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
      {partial && <><h4>Safe partial progress</h4><pre className="ds-code">{JSON.stringify(partial, null, 2)}</pre></>}
    </div>
  );
}
