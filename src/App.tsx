import { useState } from "react";

type ResolveResponse =
  | {
      ok: true;
      title: string;
      downloadUrl: string;
      qualityLabel: string;
    }
  | { ok: false; error: string; hint?: string };

export function App() {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ready">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<Extract<ResolveResponse, { ok: true }> | null>(null);

  const resolve = async () => {
    setMessage(null);
    setResult(null);
    if (!url.trim()) {
      setStatus("error");
      setMessage("Paste a YouTube link first.");
      return;
    }
    setStatus("loading");
    try {
      const res = await fetch("/api/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      let data: ResolveResponse;
      try {
        data = (await res.json()) as ResolveResponse;
      } catch {
        setStatus("error");
        setMessage(res.ok ? "Bad response" : `Request failed (${res.status})`);
        return;
      }
      if (!res.ok) {
        setStatus("error");
        setMessage(
          (data as { error?: string }).error ?? `Request failed (${res.status})`
        );
        return;
      }
      if (!data.ok) {
        setStatus("error");
        setMessage(data.hint ? `${data.error} ${data.hint}` : data.error);
        return;
      }
      setResult(data);
      setStatus("ready");
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Network error");
    }
  };

  const openDirect = () => {
    if (!result) return;
    const w = globalThis.open(result.downloadUrl, "_blank", "noopener,noreferrer");
    if (w) {
      w.opener = null;
    } else {
      setMessage("Popup blocked. Allow popups, or use Copy link.");
    }
  };

  const copyLink = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.downloadUrl);
      setMessage("Link copied. Paste it into the browser or a download manager.");
    } catch {
      setMessage("Could not access clipboard. Copy the link manually from the long URL.");
    }
  };

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>
            <span className="logo-b" />
          </span>
          <div>
            <h1>Get MP4</h1>
            <p className="sub">YouTube — progressive stream link</p>
          </div>
        </div>
      </header>

      <main className="panel">
        <div className="row">
          <input
            type="url"
            className="input"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder="https://www.youtube.com/watch?v=…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void resolve();
            }}
          />
          <button
            className="btn primary"
            type="button"
            onClick={() => void resolve()}
            disabled={status === "loading"}
          >
            {status === "loading" ? "Resolving…" : "Resolve"}
          </button>
        </div>
        {message && (
          <p className="feedback" data-tone={status === "error" ? "err" : "info"}>
            {message}
          </p>
        )}

        {result && status === "ready" && (
          <section className="result" aria-live="polite">
            <div className="result-head">
              <h2>Ready</h2>
              <span className="pill ok">{result.qualityLabel}</span>
            </div>
            <p className="title" title={result.title}>
              {result.title}
            </p>
            <div className="actions">
              <button className="btn" type="button" onClick={openDirect}>
                Open stream
              </button>
              <button className="btn ghost" type="button" onClick={() => void copyLink()}>
                Copy link
              </button>
            </div>
            <p className="hint">
              Browsers may download or play, or you can paste the link into a download tool.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
