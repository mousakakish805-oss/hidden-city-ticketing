"""English message catalog. This is the reference catalog: every key must exist
here, and the tests fail if another language drifts out of sync with it."""

from __future__ import annotations

MESSAGES_EN: dict[str, str] = {
    # ------------------------------------------------------------ disclaimer
    "disclaimer.title": "Before you use a hidden-city fare",
    "disclaimer.summary": (
        "A hidden-city fare means booking a flight to a city beyond the one you "
        "want, and getting off at the connection. The saving is real. So are "
        "the consequences of getting it wrong: this breaks the contract you "
        "agree to when you buy the ticket, and a single mistake can cost you "
        "your luggage, your flight home, or the whole fare. Read all ten points "
        "before you book."
    ),
    "disclaimer.rule.ONE_WAY_ONLY.title": "Book one-way tickets only",
    "disclaimer.rule.ONE_WAY_ONLY.body": (
        "The moment you miss one flight, the airline automatically cancels every "
        "remaining flight on that ticket. Skip the last leg of your outbound "
        "journey on a return ticket and your flight home is cancelled while you "
        "are still abroad, with no refund. If you need a return, buy it as a "
        "second, separate one-way ticket. This tool prices return trips that way "
        "for exactly this reason."
    ),
    "disclaimer.rule.CARRY_ON_ONLY.title": "Travel with cabin baggage only",
    "disclaimer.rule.CARRY_ON_ONLY.body": (
        "Checked bags are tagged to the final city printed on your ticket, not "
        "to your connection. Check a bag and it continues without you, and no "
        "airline will retrieve it for you at the stop. Take only what fits in "
        "the cabin -- and be aware that on smaller aircraft, cabin bags are "
        "sometimes taken at the gate and put in the hold, where the same problem "
        "applies."
    ),
    "disclaimer.rule.CONTRACT_OF_CARRIAGE.title": (
        "This breaks the conditions of carriage of most airlines"
    ),
    "disclaimer.rule.CONTRACT_OF_CARRIAGE.body": (
        "Almost every airline forbids deliberately skipping part of a ticket. "
        "It is not a criminal matter, but it is a breach of contract, and "
        "airlines do act on it: invoicing passengers for the difference between "
        "what they paid and the fare to the city they actually flew to, closing "
        "frequent-flyer accounts and cancelling accrued miles, and occasionally "
        "refusing to carry someone again. The risk is small once and grows with "
        "every repeat under the same name."
    ),
    "disclaimer.rule.REROUTE_RISK.title": (
        "A schedule change can send you around the city you wanted"
    ),
    "disclaimer.rule.REROUTE_RISK.body": (
        "You are buying a route, not a promise. If a flight is delayed, "
        "cancelled or retimed, the airline will rebook you to the city on your "
        "ticket by whatever path suits it -- and it has no idea you cared about "
        "the connection. You would arrive somewhere you never intended to go, "
        "with no claim. Itineraries where your city is the very first landing "
        "cannot be rerouted this way, which is why every result here carries a "
        "confidence score based on exactly that."
    ),
    "disclaimer.rule.IMMIGRATION.title": "You must be allowed to enter the city where you get off",
    "disclaimer.rule.IMMIGRATION.body": (
        "Walking out of the airport means passing through immigration, which can "
        "require a visa you would not have needed merely to change planes. Border "
        "officers may also ask why your ticket shows a flight you have no "
        "intention of taking, and some countries require proof that you are "
        "leaving again. Check the entry rules for your passport before you book, "
        "not at the airport."
    ),
    "disclaimer.rule.NO_LOYALTY_NUMBER.title": "Leave your frequent-flyer number off the booking",
    "disclaimer.rule.NO_LOYALTY_NUMBER.body": (
        "Your loyalty number is the easiest way for an airline to connect "
        "repeated no-shows to one person, and account closure is their most "
        "common response. You would not earn miles for a flight you did not take "
        "anyway, so there is nothing to lose by leaving it out."
    ),
    "disclaimer.rule.TRAVEL_INSURANCE.title": "Your travel insurance may not cover you",
    "disclaimer.rule.TRAVEL_INSURANCE.body": (
        "Most policies exclude losses that follow from deliberately breaching a "
        "contract. If something goes wrong on a journey where you intentionally "
        "skipped a flight -- missed connections, delays, disruption to onward "
        "plans -- your insurer may refuse the claim. This is the risk travellers "
        "most often overlook, because it only surfaces when something else has "
        "already gone wrong."
    ),
    "disclaimer.rule.NO_CHANGES.title": "Do not cancel or alter the leg you intend to skip",
    "disclaimer.rule.NO_CHANGES.body": (
        "Check in for the flights you are actually taking, and simply do not "
        "appear at the gate for the last one. Do not phone the airline to cancel "
        "it, and do not change the booking: either draws attention to it, and "
        "some airlines will then re-price the entire ticket at the higher fare."
    ),
    "disclaimer.rule.PASSENGER_RIGHTS.title": "You may give up your passenger rights",
    "disclaimer.rule.PASSENGER_RIGHTS.body": (
        "Compensation schemes for delays and cancellations, such as EU261, "
        "generally protect passengers who travel as ticketed. Deliberately "
        "abandoning part of your journey can put you outside that protection for "
        "the rest of the trip, and may complicate any refund you would otherwise "
        "have been owed."
    ),
    "disclaimer.rule.NOT_ADVICE.title": "This website reports prices; it does not advise you",
    "disclaimer.rule.NOT_ADVICE.body": (
        "Fares and schedules change constantly, and what you see here may "
        "already be out of date by the time you reach the airline's website. "
        "Nothing on this website is booked, sold, or reserved for you, and "
        "nothing here is legal or travel advice. How you use this information, "
        "and anything that follows from it, is your decision and your "
        "responsibility."
    ),
    # ------------------------------------------------------------------ risk
    "risk.CARRY_ON_ONLY": (
        "Carry-on baggage only. A checked bag is tagged through to "
        "{ticketed_city} and you cannot retrieve it in {deplane_city}."
    ),
    "risk.ONE_WAY_ONLY": (
        "Book as a one-way. Skipping any leg voids every remaining leg on the "
        "same ticket, including a return."
    ),
    "risk.CONTRACT_OF_CARRIAGE": (
        "Most airlines prohibit this in their conditions of carriage. Repeat use "
        "can lead to fare-difference invoices or account closure."
    ),
    "risk.NO_LOYALTY_NUMBER": (
        "Do not attach a frequent-flyer number; that is how carriers link and "
        "act on repeated no-shows."
    ),
    "risk.DIRECT_FIRST_LEG": (
        "{deplane_city} is the first arrival, so no earlier connection can be "
        "rebooked around it. This is the safest structure."
    ),
    "risk.REROUTE_RISK": (
        "{deplane_index} connection(s) happen before {deplane_city}. A delay or "
        "schedule change could rebook you to {ticketed_city} on a path that "
        "never touches {deplane_city}."
    ),
    "risk.TIGHT_CONNECTION": (
        "Only {layover_minutes} minutes of scheduled ground time in "
        "{deplane_city}; expect to be paged before the doors close."
    ),
    "risk.LONG_LAYOVER": (
        "{layover_hours}h on the ground in {deplane_city}, so walking out "
        "attracts little attention."
    ),
    "risk.MARGINAL_SAVINGS": (
        "The gap is small enough that ordinary fare movement could erase it before you book."
    ),
    "risk.LOW_AVAILABILITY": (
        "Only {bookable_seats} seat(s) left in this fare bucket; the price is likely to move."
    ),
    "risk.NOT_ONE_WAY": ("This offer has a return leg. Deplaning early would cancel it."),
    "risk.IMMIGRATION": (
        "You must be admissible to enter {deplane_city} and clear immigration "
        "there. Confirm visa rules before booking."
    ),
    # Shown to visitors when a search fails. Deliberately free of vendor
    # names, exception classes and server-side instructions -- see
    # services/errors.py.
    "error.quota": (
        "This service has reached its flight-data limit for now. Please try again later."
    ),
    "error.busy": (
        "The flight-data service is busy right now. Please wait a moment and try again."
    ),
    "error.noFlights": (
        "We could not find any flights for that route and date. Try a "
        "different date, or a nearby airport."
    ),
    "error.misconfigured": (
        "This service is temporarily unable to look up fares. Please try again later."
    ),
    "error.unreachable": (
        "We could not reach the flight-data service. Please try again in a few minutes."
    ),
    "error.unexpected": "Something went wrong while searching. Please try again.",
    # -------------------------------------------------------------- warnings
    "warning.no_candidates": (
        "No plausible onward markets found beyond {destination}. It may be a "
        "route endpoint rather than a connecting hub."
    ),
    "warning.failed_probes": (
        "{failed} of {total} extended queries failed or timed out; results may be incomplete."
    ),
    # ------------------------------------------------------- candidate reasons
    "candidate.learned": "Previously produced savings via {target}",
    "candidate.cheaper_market": ("{city} should price below {target_city} despite being further"),
    "candidate.nonstop": "{target} has nonstop service onward to {city}",
    "candidate.on_the_line": "{target} sits close to the line from {origin_city} to {city}",
    # --------------------------------------------------------------- booking
    "booking.instructions": (
        "Search {origin} to {ticketed_iata} on {date}, one way, and choose the "
        "itinerary that connects in {deplane_iata}."
    ),
    "booking.openSearch": "See this flight on Google Flights",
    "booking.openSearchNote": (
        "Opens the {origin} to {ticketed_iata} search, one way. Pick the "
        "itinerary that connects in {deplane_iata}, then book it on the "
        "airline's own site."
    ),
    "booking.no_site": (
        "We do not have a website on file for {carrier_name}. Search for their "
        "official site, or use any travel agent."
    ),
}
