/**
 * A Google Flights search, already filled in.
 *
 * The backend builds this for hidden-city options, where getting the ticketed
 * city right is load-bearing and belongs next to the analysis. An ordinary
 * A-to-B offer needs no such care — the market is exactly the one that was
 * searched — so it is assembled here rather than round-tripped.
 *
 * A plain-language query, not an internal parameter format: Google parses it,
 * and it does not rot the way an undocumented URL shape does.
 */
export function googleFlightsUrl(origin: string, destination: string, date: string): string {
  const query = `Flights from ${origin} to ${destination} on ${date} one way`;
  return `https://www.google.com/travel/flights?q=${encodeURIComponent(query)}`;
}
