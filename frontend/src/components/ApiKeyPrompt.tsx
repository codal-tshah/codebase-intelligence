import { KeyRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AUTH_REQUIRED_EVENT, getApiKey, setApiKey } from "../api";

/**
 * Shown when the API answers 401 (server mode, `CI_MODE=server`). The key is kept for this tab
 * only (sessionStorage) and sent as `X-API-Key`. Reloading afterwards re-runs every request.
 */
export function ApiKeyPrompt() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [rejected, setRejected] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onAuth = () => {
      setRejected(Boolean(getApiKey()));
      setOpen(true);
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuth);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuth);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  if (!open) return null;
  return (
    <div className="palette-backdrop" role="presentation">
      <form
        className="auth-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
        onSubmit={(e) => {
          e.preventDefault();
          if (!value.trim()) return;
          setApiKey(value.trim());
          window.location.reload();
        }}
      >
        <h2 id="auth-title">
          <KeyRound size={18} strokeWidth={1.5} aria-hidden /> API key required
        </h2>
        <p className="muted">
          This server runs in server mode. Enter the API key from your administrator (<code>CI_API_KEY</code>). It is
          kept in this browser tab only and cleared when the tab closes.
        </p>
        {rejected ? (
          <p className="form-error" role="alert">
            The saved key was rejected. Check it and try again.
          </p>
        ) : null}
        <label className="field-label" htmlFor="auth-key">
          API key
        </label>
        <input
          id="auth-key"
          ref={inputRef}
          type="password"
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <div className="auth-actions">
          <button type="submit" className="btn primary" disabled={!value.trim()}>
            Continue
          </button>
        </div>
      </form>
    </div>
  );
}
