import { useEffect, useRef, useState } from "react";
import { Mic, Loader2 } from "lucide-react";

/**
 * Click-to-record mic button.
 *
 * Unlike browser MediaRecorder (which WKWebView gates behind entitlements),
 * this button just kicks the BACKEND to record for N seconds via sounddevice.
 * Reliable on macOS because Python's sounddevice already has the system
 * permission (granted the first time the user ran `make phase5-voice`).
 *
 * Flow:
 *   click → call onStart (caller hits /api/voice/live which blocks until done)
 *   → countdown displays in the button
 *   → onStart's promise resolves when the full pipeline is back
 */
export function MicButton({
  seconds = 5,
  onRecord,
  disabled,
}: {
  seconds?: number;
  onRecord: () => Promise<void>;
  disabled?: boolean;
}) {
  const [state, setState] = useState<"idle" | "recording" | "processing">("idle");
  const [remaining, setRemaining] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function go() {
    if (state !== "idle" || disabled) return;

    // UI countdown, purely cosmetic, mirrors the server's record duration.
    setState("recording");
    setRemaining(seconds);
    const startedAt = Date.now();
    timerRef.current = window.setInterval(() => {
      const left = seconds - (Date.now() - startedAt) / 1000;
      if (left <= 0) {
        setState((s) => (s === "recording" ? "processing" : s));
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = null;
      } else {
        setRemaining(left);
      }
    }, 100);

    try {
      await onRecord();
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      setState("idle");
      setRemaining(0);
    }
  }

  const Icon = state === "processing" ? Loader2 : Mic;
  const label =
    state === "recording"
      ? `${Math.ceil(remaining)}s`
      : state === "processing"
      ? ""
      : "";

  return (
    <button
      onClick={go}
      disabled={disabled || state !== "idle"}
      className={
        "relative w-[52px] flex items-center justify-center px-3 py-3 rounded-xl transition-all disabled:opacity-40 font-mono text-xs " +
        (state === "recording"
          ? "bg-accent text-white"
          : state === "processing"
          ? "bg-surface-deep text-ink"
          : "bg-surface-deep text-ink hover:bg-ink hover:text-white")
      }
      aria-label={state === "recording" ? "recording" : "record voice query"}
      title={state === "idle" ? `record ${seconds}s voice query` : "recording…"}
    >
      {state === "recording" ? (
        <span>{label}</span>
      ) : (
        <Icon size={18} className={state === "processing" ? "animate-spin" : ""} />
      )}
    </button>
  );
}
