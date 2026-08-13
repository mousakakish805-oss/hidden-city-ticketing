"""Official booking sites, keyed by airline IATA code.

Curated by hand because the OpenFlights dump carries no websites. Kept separate
from ``generated/`` so it survives a dataset rebuild and can be corrected
without regenerating anything.

Deliberately homepages, not deep links into booking flows: every airline's
search URL differs, and those query formats change without notice. A link that
lands on the airline's own site plus explicit "search X to Y, one way" wording
stays correct; a fabricated deep link quietly breaks. An airline that is absent
here simply gets no link.
"""

from __future__ import annotations

AIRLINE_SITES: dict[str, str] = {
    # ------------------------------------------------- Middle East / Levant
    "TK": "https://www.turkishairlines.com",
    "PC": "https://www.flypgs.com",
    "RJ": "https://www.rj.com",
    "ME": "https://www.mea.com.lb",
    "MS": "https://www.egyptair.com",
    "LY": "https://www.elal.com",
    "CY": "https://www.cyprusairways.com",
    # ------------------------------------------------------------- Gulf
    "EK": "https://www.emirates.com",
    "EY": "https://www.etihad.com",
    "QR": "https://www.qatarairways.com",
    "SV": "https://www.saudia.com",
    "GF": "https://www.gulfair.com",
    "KU": "https://www.kuwaitairways.com",
    "WY": "https://www.omanair.com",
    "FZ": "https://www.flydubai.com",
    "G9": "https://www.airarabia.com",
    "J9": "https://www.jazeeraairways.com",
    "XY": "https://www.flynas.com",
    # ------------------------------------------------------------ Europe
    "LH": "https://www.lufthansa.com",
    "AF": "https://www.airfrance.com",
    "KL": "https://www.klm.com",
    "BA": "https://www.britishairways.com",
    "VS": "https://www.virginatlantic.com",
    "LX": "https://www.swiss.com",
    "OS": "https://www.austrian.com",
    "SN": "https://www.brusselsairlines.com",
    "IB": "https://www.iberia.com",
    "UX": "https://www.aireuropa.com",
    "TP": "https://www.flytap.com",
    "AZ": "https://www.ita-airways.com",
    "A3": "https://en.aegeanair.com",
    "LO": "https://www.lot.com",
    "OK": "https://www.csa.cz",
    "SK": "https://www.flysas.com",
    "AY": "https://www.finnair.com",
    "BT": "https://www.airbaltic.com",
    "DY": "https://www.norwegian.com",
    "FI": "https://www.icelandair.com",
    "EI": "https://www.aerlingus.com",
    "JU": "https://www.airserbia.com",
    "OU": "https://www.croatiaairlines.com",
    "FB": "https://www.air.bg",
    "RO": "https://www.tarom.ro",
    "W6": "https://wizzair.com",
    "FR": "https://www.ryanair.com",
    "U2": "https://www.easyjet.com",
    "VY": "https://www.vueling.com",
    "SU": "https://www.aeroflot.ru",
    "PS": "https://www.flyuia.com",
    # -------------------------------------------------- Caucasus / Central Asia
    "A9": "https://www.georgian-airways.com",
    "J2": "https://www.azal.az",
    "HY": "https://www.uzairways.com",
    "KC": "https://airastana.com",
    # ------------------------------------------------------------ Africa
    "ET": "https://www.ethiopianairlines.com",
    "KQ": "https://www.kenya-airways.com",
    "SA": "https://www.flysaa.com",
    "AT": "https://www.royalairmaroc.com",
    "TU": "https://www.tunisair.com",
    "AH": "https://airalgerie.dz",
    # ------------------------------------------------------- South Asia
    "AI": "https://www.airindia.com",
    "6E": "https://www.goindigo.in",
    "PK": "https://www.piac.com.pk",
    "UL": "https://www.srilankan.com",
    # --------------------------------------------------------- East Asia
    "TG": "https://www.thaiairways.com",
    "SQ": "https://www.singaporeair.com",
    "MH": "https://www.malaysiaairlines.com",
    "AK": "https://www.airasia.com",
    "CX": "https://www.cathaypacific.com",
    "KE": "https://www.koreanair.com",
    "OZ": "https://flyasiana.com",
    "NH": "https://www.ana.co.jp",
    "JL": "https://www.jal.co.jp",
    "CA": "https://www.airchina.com",
    "MU": "https://www.ceair.com",
    "CZ": "https://www.csair.com",
    "BR": "https://www.evaair.com",
    "CI": "https://www.china-airlines.com",
    "VN": "https://www.vietnamairlines.com",
    "PR": "https://www.philippineairlines.com",
    "GA": "https://www.garuda-indonesia.com",
    "BI": "https://www.flyroyalbrunei.com",
    # ---------------------------------------------------- North America
    "AA": "https://www.aa.com",
    "DL": "https://www.delta.com",
    "UA": "https://www.united.com",
    "AS": "https://www.alaskaair.com",
    "B6": "https://www.jetblue.com",
    "WN": "https://www.southwest.com",
    "AC": "https://www.aircanada.com",
    "WS": "https://www.westjet.com",
    "AM": "https://www.aeromexico.com",
    # ------------------------------------- South America / Oceania
    "AV": "https://www.avianca.com",
    "LA": "https://www.latamairlines.com",
    "JJ": "https://www.latamairlines.com",
    "AR": "https://www.aerolineas.com.ar",
    "G3": "https://www.voegol.com.br",
    "AD": "https://www.voeazul.com.br",
    "QF": "https://www.qantas.com",
    "NZ": "https://www.airnewzealand.com",
}


def booking_site(iata: str | None) -> str | None:
    if not iata:
        return None
    return AIRLINE_SITES.get(iata.strip().upper())
