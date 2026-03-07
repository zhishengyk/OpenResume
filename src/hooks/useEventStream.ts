import { useEffect } from "react";
import { apiBaseUrl } from "../lib/api";
import type { SearchEvent } from "../types";

export function useEventStream(
  sessionId: string | undefined,
  onEvent: (event: SearchEvent) => void,
) {
  useEffect(() => {
    if (!sessionId) {
      return;
    }

    const source = new EventSource(
      `${apiBaseUrl}/api/search-sessions/${sessionId}/events`,
    );

    source.onmessage = (message) => {
      onEvent(JSON.parse(message.data) as SearchEvent);
    };

    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
    };
  }, [onEvent, sessionId]);
}

