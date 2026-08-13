/** Mirrors the FastAPI response payloads. Kept in one file so API drift shows
 *  up as type errors in exactly one place. */

export type Cabin = "ECONOMY" | "PREMIUM_ECONOMY" | "BUSINESS" | "FIRST";
export type Severity = "critical" | "warning" | "info";
export type ConfidenceBand = "high" | "medium" | "low";

export interface Airport {
  iata: string;
  name: string;
  city: string;
  country: string;
  country_code: string | null;
  region: string;
  lat: number;
  lon: number;
  hub_tier: number;
  destination_count: number;
  carrier_count: number;
  label: string;
}

export interface Airline {
  iata: string;
  name: string;
  country: string;
  active: boolean;
  icao: string | null;
  label: string;
}

export interface Country {
  name: string;
  code: string | null;
  region: string;
  airport_count: number;
}

export interface Coverage {
  airports: number;
  airports_with_scheduled_service: number;
  airlines: number;
  active_airlines: number;
  countries: number;
  regions: number;
  directed_routes: number;
  hub_tiers: Record<string, number>;
  source: string;
}

export interface Segment {
  origin: string;
  destination: string;
  departure_at: string;
  arrival_at: string;
  carrier: string;
  carrier_name: string;
  flight_number: string;
  duration_minutes: number;
  duration_label: string;
  aircraft: string | null;
  operating_carrier: string | null;
  cabin: string | null;
}

export interface Itinerary {
  segments: Segment[];
  duration_minutes: number;
  duration_label: string;
  stop_count: number;
  path: string[];
}

export interface Offer {
  provider: string;
  offer_id: string;
  search_origin: string;
  search_destination: string;
  departure_date: string;
  price_total: number;
  currency: string;
  itineraries: Itinerary[];
  validating_carriers: string[];
  cabin: string;
  bookable_seats: number | null;
  primary_carrier: string;
  primary_carrier_name: string;
  stop_count: number;
  duration_minutes: number;
  duration_label: string;
}

export interface RiskFlag {
  code: string;
  severity: Severity;
  message: string;
}

export interface RiskAssessment {
  confidence: number;
  band: ConfidenceBand;
  flags: RiskFlag[];
}

export interface BookingGuidance {
  carrier: string;
  carrier_name: string;
  /** Official airline site, or null when we have no verified URL on file. */
  url: string | null;
  instructions: string;
  note: string | null;
}

export interface HiddenCityOption {
  ticketed_iata: string;
  ticketed_city: string;
  deplane_iata: string;
  deplane_city: string;
  price: number;
  baseline_price: number;
  savings: number;
  savings_percent: number;
  currency: string;
  carrier: string;
  deplane_index: number;
  segments_before_target: number;
  segments_after_target: number;
  layover_minutes: number | null;
  usable_duration_minutes: number;
  usable_duration_label: string;
  usable_arrival: string;
  is_nearby_airport: boolean;
  risk: RiskAssessment;
  booking: BookingGuidance;
  offer: Offer;
}

export interface CandidateRoute {
  iata: string;
  city: string;
  country: string;
  source: "route" | "learned" | "geometric";
  score: number;
  detour_ratio: number;
  onward_km: number;
  total_km: number;
  served_nonstop: boolean;
  reason: string;
}

export interface ProbeResult {
  destination: string;
  offer_count: number;
  min_price: number | null;
  error: string | null;
  from_cache: boolean;
  elapsed_ms: number;
}

export interface PriceMatrixRow {
  iata: string;
  city: string;
  is_target: boolean;
  cheapest: number;
  prices: (number | null)[];
}

export interface PriceMatrix {
  destinations: string[];
  carriers: string[];
  rows: PriceMatrixRow[];
  currency: string | null;
}

export interface MarketStat {
  iata: string;
  city: string;
  country: string | null;
  is_target: boolean;
  offer_count: number;
  min_price: number;
  median_price: number;
  max_price: number;
  carriers: number;
  min_stops: number;
}

export interface DisclaimerRule {
  code: string;
  severity: Severity;
  required: boolean;
  title: string;
  body: string;
}

export interface Disclaimer {
  version: string;
  language: "en" | "ar";
  title: string;
  summary: string;
  rules: DisclaimerRule[];
  required_codes: string[];
}

export interface SearchParams {
  origin: string;
  destination: string;
  departure_date: string;
  /** Set for a return trip. Priced as two separate one-way tickets. */
  return_date: string | null;
  adults: number;
  cabin: Cabin;
  currency: string;
  include_nearby_airports: boolean;
  refresh: boolean;
  /** Language for server-rendered text: disclaimer, risk flags, booking steps. */
  lang: "en" | "ar";
}

/** One direction of a trip, priced and analysed on its own. */
export interface LegResult {
  leg: "outbound" | "inbound";
  origin: string;
  destination: string;
  departure_date: string;
  origin_airport: { iata: string; city: string; country: string | null };
  destination_airport: { iata: string; city: string; country: string | null };
  baseline: {
    price: number | null;
    currency: string;
    offer_count: number;
    offers: Offer[];
  };
  hidden_city: {
    count: number;
    best_savings: number | null;
    best_savings_percent: number | null;
    rejected_count: number;
    options: HiddenCityOption[];
  };
  candidates: CandidateRoute[];
  probes: ProbeResult[];
  price_matrix: PriceMatrix;
  market_stats: MarketStat[];
}

export interface TripTotals {
  currency: string;
  baseline: number | null;
  best: number | null;
  savings: number | null;
  legs_with_savings?: number;
}

/** The outbound leg's fields are also spread at the top level, so a one-way
 *  response keeps exactly the shape it had before return trips existed. */
export interface SearchResult extends LegResult {
  search_id: string;
  status: "complete";
  generated_at: string;
  provider: string;
  language: "en" | "ar";
  direction: "ltr" | "rtl";
  trip_type: "one_way" | "round_trip";
  duration_ms: number;
  query: SearchParams & {
    origin_airport: { iata: string; city: string; country: string | null };
    destination_airport: { iata: string; city: string; country: string | null };
  };
  outbound: LegResult;
  inbound: LegResult | null;
  totals: TripTotals | null;
  disclaimer: Disclaimer;
  warnings: string[];
}

export interface Health {
  status: "ok" | "degraded";
  provider: string;
  provider_live: boolean;
  /** Requests left on a metered plan; null when the provider publishes none. */
  provider_quota_remaining: number | null;
  database: string;
  database_reachable: boolean;
  disclaimer_version: string;
  version: string;
}

/** Progress events pushed over SSE while the batch engine runs. */
export type SearchEvent =
  | { type: "started"; query: SearchParams }
  | { type: "baseline"; price: number; currency: string; offer_count: number; from_cache: boolean }
  | { type: "candidates"; count: number; candidates: CandidateRoute[] }
  | { type: "probe_started"; destination: string }
  | ({ type: "probe_finished" } & ProbeResult)
  | { type: "complete"; search_id: string; hidden_option_count: number; best_savings: number | null; duration_ms: number }
  | { type: "failed"; error: string };
