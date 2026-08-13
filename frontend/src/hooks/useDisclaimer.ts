import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import type { Disclaimer } from "../types";

const ACK_KEY = "hct.disclaimer.version";
const TOKEN_KEY = "hct.client.token";

function clientToken(): string {
  let token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    token = crypto.randomUUID();
    localStorage.setItem(TOKEN_KEY, token);
  }
  return token;
}

/**
 * Loads the versioned disclaimer and tracks acceptance.
 *
 * Acceptance is stored against the *version*, so publishing new wording
 * automatically re-prompts everyone. Hidden-city results stay hidden until
 * this returns `accepted`. Acceptance deliberately survives a language switch:
 * the rules are the same rules, and re-prompting would train people to click
 * through them.
 */
export function useDisclaimer(lang: string) {
  const [disclaimer, setDisclaimer] = useState<Disclaimer | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .disclaimer(lang)
      .then((payload) => {
        if (cancelled) return;
        setDisclaimer(payload);
        setAccepted(localStorage.getItem(ACK_KEY) === payload.version);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [lang]);

  const accept = useCallback(
    (searchId: string | null) => {
      if (!disclaimer) return;
      localStorage.setItem(ACK_KEY, disclaimer.version);
      setAccepted(true);
      setOpen(false);
      // Server-side audit trail; a failure here must not block the user.
      void api
        .acknowledge(searchId ?? "none", clientToken(), disclaimer.version)
        .catch(() => undefined);
    },
    [disclaimer],
  );

  return { disclaimer, accepted, open, setOpen, accept };
}
