import { Fragment } from "react";

import type { Itinerary } from "../types";

interface Props {
  itinerary: Itinerary;
  /** Airport the traveller actually leaves at; everything after it is dead weight. */
  deplaneIata?: string;
}

/** Renders the routing, striking through the legs the traveller will skip.
 *
 *  Forced left-to-right even in Arabic: a route is a sequence of airport codes
 *  read in travel order, and mirroring it would reverse the journey.
 */
export function SegmentTimeline({ itinerary, deplaneIata }: Props) {
  const path = itinerary.path;
  const deplaneAt = deplaneIata ? path.indexOf(deplaneIata) : -1;
  const hasSkip = deplaneAt > 0 && deplaneAt < path.length - 1;

  return (
    <div dir="ltr" className="flex items-center gap-1 flex-wrap text-sm">
      {path.map((code, index) => {
        const isDeplane = hasSkip && index === deplaneAt;
        const isSkipped = hasSkip && index > deplaneAt;
        return (
          <Fragment key={`${code}-${index}`}>
            {index > 0 && (
              <span className={isSkipped ? "text-ink-faint" : "text-ink-faint"} aria-hidden="true">
                {isSkipped ? "⇢" : "→"}
              </span>
            )}
            <span
              className={`font-mono font-bold px-1.5 py-0.5 rounded ${
                isDeplane
                  ? "bg-positive-soft text-positive ring-1 ring-positive-line"
                  : isSkipped
                    ? "text-ink-faint line-through"
                    : "text-ink"
              }`}
            >
              {code}
            </span>
          </Fragment>
        );
      })}
    </div>
  );
}
