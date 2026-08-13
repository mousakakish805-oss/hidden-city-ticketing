import { useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "../i18n";
import { api, ApiError } from "../lib/api";
import type { SearchEvent, SearchParams, SearchResult } from "../types";

const EVENT_NAMES = [
  "started",
  "baseline",
  "candidates",
  "probe_started",
  "probe_finished",
  "complete",
  "failed",
] as const;

interface SearchState {
  busy: boolean;
  events: SearchEvent[];
  result: SearchResult | null;
  error: string | null;
}

const IDLE: SearchState = { busy: false, events: [], result: null, error: null };

/**
 * Runs a search and follows the batch engine live.
 *
 * The backend queues the run and streams progress over SSE; the full result is
 * fetched once the `complete` event lands. That keeps a 10-20 second fan-out
 * feeling like visible work rather than a frozen spinner.
 */
export function useSearch() {
  const [state, setState] = useState<SearchState>(IDLE);
  const sourceRef = useRef<EventSource | null>(null);
  const { t } = useI18n();

  const closeStream = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  // Never leave a stream open behind an unmounted component.
  useEffect(() => closeStream, [closeStream]);

  const search = useCallback(
    async (params: SearchParams) => {
      closeStream();
      setState({ ...IDLE, busy: true });

      let searchId: string;
      try {
        ({ search_id: searchId } = await api.startSearch(params));
      } catch (error) {
        setState({
          ...IDLE,
          error: error instanceof ApiError ? error.message : t("error.unreachable"),
        });
        return;
      }
      // Validation and provider errors arrive from the API already translated
      // and already stripped of anything internal. A transport failure never
      // reaches the API at all, so that one is worded here.

      const source = new EventSource(api.eventStreamUrl(searchId));
      sourceRef.current = source;

      const handle = (message: MessageEvent<string>) => {
        const event = JSON.parse(message.data) as SearchEvent;
        setState((previous) => ({ ...previous, events: [...previous.events, event] }));

        if (event.type === "complete") {
          closeStream();
          api
            .getSearch(searchId)
            .then((result) => setState((previous) => ({ ...previous, result, busy: false })))
            .catch((error: unknown) =>
              setState((previous) => ({
                ...previous,
                busy: false,
                error: error instanceof ApiError ? error.message : t("error.result"),
              })),
            );
        }

        if (event.type === "failed") {
          closeStream();
          setState((previous) => ({ ...previous, busy: false, error: event.error }));
        }
      };

      for (const name of EVENT_NAMES) {
        source.addEventListener(name, handle as EventListener);
      }

      source.onerror = () => {
        // Fires on normal stream close too, so only surface it if nothing landed.
        closeStream();
        setState((previous) =>
          previous.result || previous.error
            ? { ...previous, busy: false }
            : { ...previous, busy: false, error: t("error.stream") },
        );
      };
    },
    [closeStream, t],
  );

  const reset = useCallback(() => {
    closeStream();
    setState(IDLE);
  }, [closeStream]);

  return { ...state, search, reset };
}
