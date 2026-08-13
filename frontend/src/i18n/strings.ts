/**
 * UI copy in both languages, side by side so drift is obvious in review.
 *
 * Only *chrome* lives here. Disclaimer text, risk warnings and booking
 * guidance come from the API already translated — they interpolate live values
 * and the disclaimer is versioned and legally load-bearing, so it has one
 * authoritative source rather than two.
 */

export type Lang = "en" | "ar";

export const LANGUAGES: { code: Lang; name: string; dir: "ltr" | "rtl" }[] = [
  { code: "en", name: "English", dir: "ltr" },
  { code: "ar", name: "العربية", dir: "rtl" },
];

const en = {
  "app.title": "Hidden-City Ticketing",
  "app.subtitle": "Multi-segment flight price comparison",
  "app.coverage": "{airports} airports · {countries} countries",

  "header.rules": "Rules & risks",
  "header.live": "live fares",
  "header.synthetic": "test data",
  "header.liveHint": "Live fares from {provider}",
  "header.syntheticHint": "Synthetic fares. Add provider credentials for live pricing.",
  "header.language": "Language",
  "header.quota": "{count} left",
  "header.quotaHint": "{count} API requests remaining on your plan this period.",
  "header.quotaEmpty": "quota spent",
  "header.quotaEmptyHint":
    "Your provider plan has no requests left this period. Searches will fail until it resets or you upgrade.",

  "form.from": "From",
  "form.to": "To",
  "form.toHint": "where you actually want to go",
  "form.tripType": "Trip",
  "form.oneWay": "One way",
  "form.roundTrip": "Two way",
  "form.departure": "Departure",
  "form.returnDate": "Coming back",
  "form.returnBeforeDeparture": "The return date cannot be before you leave.",
  "form.twoTicketsNote":
    "A return is priced as two separate one-way tickets — the only way a hidden-city fare can be used safely. It also doubles the API calls.",

  "trip.outbound": "Outbound",
  "trip.inbound": "Return",
  "trip.outboundRoute": "{from} to {to}",
  "trip.totalNormal": "Both tickets, normal fares",
  "trip.totalBest": "Both tickets, best fares",
  "trip.totalSaving": "You save {amount} across the trip",
  "trip.savingsOnOneLeg": "Savings found on one direction only.",
  "trip.savingsOnBoth": "Savings found on both directions.",
  "trip.noSavings": "No hidden-city savings on either direction.",
  "trip.separateTickets":
    "Buy these as two separate one-way tickets. Never book them as one round-trip — skipping a leg would cancel your flight home.",
  "form.search": "Find anomalies",
  "form.searching": "Scanning…",
  "form.passengers": "Passengers",
  "form.cabin": "Cabin",
  "form.nearby": "Accept nearby airports",
  "form.nearbyHint": "e.g. accept landing at SAW when you asked for IST",
  "form.bypassCache": "Bypass cache",
  "form.bypassCacheHint": "Ignore cached fares and re-query the provider",
  "form.sameAirports": "Origin and destination must differ.",

  // Durations are formatted client-side from `duration_minutes` so they follow
  // the active language; the API's `duration_label` is English-only.
  "duration.hoursMinutes": "{h}h {m}m",
  "duration.minutes": "{m}m",

  "cabin.ECONOMY": "Economy",
  "cabin.PREMIUM_ECONOMY": "Premium economy",
  "cabin.BUSINESS": "Business",
  "cabin.FIRST": "First",

  "progress.title": "Batch engine",
  "progress.starting": "Starting the batch engine…",
  "progress.probed": "{done}/{total} onward markets priced",
  "progress.baseline": "Baseline direct fare {price} across {count} offers",
  "progress.cached": "served from cache",

  "results.opportunities_one": "1 hidden-city opportunity",
  "results.opportunities_other": "{count} hidden-city opportunities",
  "results.bestSaving": "Best saving {amount}",
  "results.noneTitle": "No hidden-city savings found",
  "results.noneBody":
    "Flying direct to {city} is already the cheapest way there. We priced {probes} onward markets beyond it.",
  "results.noneRejected":
    "We found {count} routing(s) through {target} that did not beat the direct fare by enough to be worth the risk.",

  "locked.title": "{count} option(s) found, saving up to {amount}",
  "locked.body":
    "Hidden-city ticketing carries rules that void your ticket if you break them. Read them before these results are shown.",
  "locked.button": "Read the rules to continue",

  "card.badge": "Hidden-city alternative",
  "card.bookTo": "Book to {city}",
  "card.getOffAt": "Get off at {city}",
  "card.yourDestination": "your actual destination",
  "card.nearbyWarning": "nearby airport, not your exact one",
  "card.save": "Save {amount} ({percent}%)",
  "card.youSkip": "you skip this",
  "card.travelTime": "Your travel time",
  "card.arrive": "You arrive",
  "card.airline": "Airline",
  "card.groundTime": "Ground time at your stop",
  "card.confidence": "{score}/100 confidence",
  "card.showAll": "Show all {count} warnings",
  "card.showCritical": "Show only critical warnings",

  "confidence.high":
    "Low execution risk: your city is reached before any connection that could be rerouted.",
  "confidence.medium": "Workable, but a connection before your city adds reroute risk.",
  "confidence.low": "Fragile: the airline could easily route you around the city you want.",

  "booking.title": "How to book this",
  "booking.openSite": "Open {airline} ↗",
  "booking.note": "We only show prices. You book on the airline's own site.",

  "standard.title": "Standard flights to {city}",
  "standard.subtitle": "What an ordinary search shows: {count} offers from {price}",
  "standard.cheapest": "cheapest direct",
  "standard.nonstop": "nonstop",
  "standard.stops_one": "1 stop",
  "standard.stops_other": "{count} stops",

  "matrix.title": "Comparative price matrix",
  "matrix.subtitle":
    "Cheapest fare per ticketed destination and airline. Anything cheaper than your target row is a city you can fly past it to, for less.",
  "matrix.ticketedTo": "Ticketed to",
  "matrix.best": "Best",
  "matrix.yourTarget": "your target",

  "modal.versionNote": "Version {version}. Tick the {count} critical rules to continue.",
  "modal.accept": "I understand the risks",
  "modal.close": "Close",

  "empty.intro":
    "Enter where you are and where you actually want to go. We price the direct route, then price flights that continue past your destination — and show you when the longer trip costs less.",

  "footer.meta": "Provider: {provider} · {probes} markets priced in {ms} ms · generated {time}",

  "error.generic": "Something went wrong.",
  "error.unreachable": "Could not reach the API. Is the backend running?",
  "error.stream": "Lost connection to the search stream.",

  "theme.toDark": "Switch to the dark theme",
  "theme.toLight": "Switch to the light theme",

  "nav.search": "Search",
  "nav.results": "Results",
  "nav.rules": "Rules & risks",
  "nav.newSearch": "New search",
  "nav.backToResults": "Back to results",

  "rules.loading": "Loading the rules…",
  "rules.version": "Version {version}. These rules are versioned; if they change, you will be asked to read them again.",
  "rules.howTitle": "How a hidden-city fare works",
  "rules.howBody":
    "Airlines price a journey by where the ticket ends, not by how far the aircraft carries you. A hub an airline dominates can therefore cost more to fly to than a smaller city on the far side of it. So you buy the ticket to the further city, fly the first leg, and simply walk out at the connection — the city you actually wanted.",
  "rules.diagramNote": "buy to SKP, get off at IST, never board the second flight",
  "rules.group.critical": "Get these wrong and it costs you",
  "rules.group.warning": "Understand these before you book",
  "rules.group.info": "Worth knowing",
  "rules.mustAccept": "Must be acknowledged before results are shown",
  "rules.checklistTitle": "Before you book, check all five",
  "rules.checklist.one": "The ticket is a one-way. If you need a return, buy it separately.",
  "rules.checklist.two": "Everything you are taking fits in the cabin.",
  "rules.checklist.three": "Your passport allows you to enter the city where you get off.",
  "rules.checklist.four": "Your frequent-flyer number is not on the booking.",
  "rules.checklist.five": "The city you want is the first landing, or you accept the reroute risk.",
  "rules.acceptAll": "I have read and understood all of this",
  "rules.alreadyAccepted": "You have accepted these rules",
  "rules.back": "Go back",
} as const;

export type StringKey = keyof typeof en;

const ar: Record<StringKey, string> = {
  "app.title": "تذاكر الوجهة المخفية",
  "app.subtitle": "مقارنة أسعار الرحلات متعددة المراحل",
  "app.coverage": "{airports} مطار · {countries} دولة",

  "header.rules": "القواعد والمخاطر",
  "header.live": "أسعار حقيقية",
  "header.synthetic": "بيانات تجريبية",
  "header.liveHint": "أسعار حقيقية من {provider}",
  "header.syntheticHint": "أسعار تجريبية. أضف بيانات اعتماد المزوّد للحصول على أسعار حقيقية.",
  "header.language": "اللغة",
  "header.quota": "بقي {count}",
  "header.quotaHint": "عدد طلبات الواجهة البرمجية المتبقية في خطتك لهذه الفترة: {count}.",
  "header.quotaEmpty": "نفدت الحصة",
  "header.quotaEmptyHint":
    "لم يتبق في خطة المزوّد أي طلبات لهذه الفترة. ستفشل عمليات البحث حتى تتجدد الخطة أو تقوم بترقيتها.",

  "form.from": "من",
  "form.to": "إلى",
  "form.toHint": "الوجهة التي تريدها فعلاً",
  "form.tripType": "نوع الرحلة",
  "form.oneWay": "ذهاب فقط",
  "form.roundTrip": "ذهاب وعودة",
  "form.departure": "تاريخ المغادرة",
  "form.returnDate": "تاريخ العودة",
  "form.returnBeforeDeparture": "لا يمكن أن يسبق تاريخ العودة تاريخ المغادرة.",
  "form.twoTicketsNote":
    "تُسعَّر رحلة الذهاب والعودة كتذكرتين منفصلتين لكل اتجاه، وهي الطريقة الوحيدة لاستخدام سعر الوجهة المخفية بأمان. كما أنها تضاعف عدد طلبات الواجهة البرمجية.",

  "trip.outbound": "الذهاب",
  "trip.inbound": "العودة",
  "trip.outboundRoute": "من {from} إلى {to}",
  "trip.totalNormal": "التذكرتان بالأسعار الاعتيادية",
  "trip.totalBest": "التذكرتان بأفضل الأسعار",
  "trip.totalSaving": "توفّر {amount} على الرحلة كاملة",
  "trip.savingsOnOneLeg": "وجدنا توفيراً في اتجاه واحد فقط.",
  "trip.savingsOnBoth": "وجدنا توفيراً في الاتجاهين.",
  "trip.noSavings": "لا يوجد توفير عبر الوجهة المخفية في أي من الاتجاهين.",
  "trip.separateTickets":
    "اشترِ هاتين كتذكرتين منفصلتين لكل اتجاه. لا تحجزهما أبداً كتذكرة ذهاب وعودة واحدة، فتخطي أي جزء سيلغي رحلة عودتك.",
  "form.search": "ابحث عن الفروقات",
  "form.searching": "جارٍ البحث…",
  "form.passengers": "المسافرون",
  "form.cabin": "الدرجة",
  "form.nearby": "اقبل المطارات القريبة",
  "form.nearbyHint": "مثلاً قبول النزول في SAW عند طلب IST",
  "form.bypassCache": "تجاهل الذاكرة المؤقتة",
  "form.bypassCacheHint": "تجاهل الأسعار المحفوظة وأعد الاستعلام من المزوّد",
  "form.sameAirports": "يجب أن تختلف نقطة الانطلاق عن الوجهة.",

  "duration.hoursMinutes": "{h} س {m} د",
  "duration.minutes": "{m} د",

  "cabin.ECONOMY": "السياحية",
  "cabin.PREMIUM_ECONOMY": "السياحية المميزة",
  "cabin.BUSINESS": "رجال الأعمال",
  "cabin.FIRST": "الأولى",

  "progress.title": "محرّك البحث المتوازي",
  "progress.starting": "جارٍ تشغيل محرّك البحث…",
  "progress.probed": "تم تسعير {done} من {total} من الأسواق اللاحقة",
  "progress.baseline": "السعر المباشر المرجعي {price} من بين {count} عرضاً",
  "progress.cached": "من الذاكرة المؤقتة",

  "results.opportunities_one": "فرصة وجهة مخفية واحدة",
  "results.opportunities_other": "عدد فرص الوجهة المخفية: {count}",
  "results.bestSaving": "أعلى توفير {amount}",
  "results.noneTitle": "لم نجد أي توفير عبر الوجهة المخفية",
  "results.noneBody":
    "الرحلة المباشرة إلى {city} هي أصلاً أرخص طريقة للوصول. سعّرنا {probes} من الأسواق اللاحقة بعدها.",
  "results.noneRejected":
    "وجدنا {count} مساراً يمر بـ {target} لكنه لم يقل عن السعر المباشر بما يكفي ليستحق المخاطرة.",

  "locked.title": "وجدنا {count} خياراً، بتوفير يصل إلى {amount}",
  "locked.body":
    "لحجز الوجهة المخفية قواعد تُبطل تذكرتك إذا خالفتها. اقرأها قبل أن تظهر لك هذه النتائج.",
  "locked.button": "اقرأ القواعد للمتابعة",

  "card.badge": "بديل الوجهة المخفية",
  "card.bookTo": "احجز إلى {city}",
  "card.getOffAt": "انزل في {city}",
  "card.yourDestination": "وجهتك الحقيقية",
  "card.nearbyWarning": "مطار قريب، وليس المطار الذي طلبته",
  "card.save": "وفّر {amount} ({percent}%)",
  "card.youSkip": "تتخطى هذه",
  "card.travelTime": "مدة سفرك",
  "card.arrive": "وقت وصولك",
  "card.airline": "شركة الطيران",
  "card.groundTime": "مدة التوقف في محطتك",
  "card.confidence": "درجة الثقة {score}/100",
  "card.showAll": "اعرض كل التحذيرات ({count})",
  "card.showCritical": "اعرض التحذيرات الحرجة فقط",

  "confidence.high":
    "مخاطر تنفيذ منخفضة: تصل إلى مدينتك قبل أي محطة توقف يمكن أن يُحوّل مسارك عبرها.",
  "confidence.medium": "ممكن، لكن وجود محطة توقف قبل مدينتك يزيد خطر تحويل المسار.",
  "confidence.low": "هشّ: تستطيع شركة الطيران بسهولة أن تحوّل مسارك بعيداً عن المدينة التي تريدها.",

  "booking.title": "كيف تحجز هذه الرحلة",
  "booking.openSite": "افتح موقع {airline} ↗",
  "booking.note": "نحن نعرض الأسعار فقط. الحجز يتم على موقع شركة الطيران نفسها.",

  "standard.title": "الرحلات الاعتيادية إلى {city}",
  "standard.subtitle": "ما يعرضه البحث العادي: {count} عرضاً ابتداءً من {price}",
  "standard.cheapest": "أرخص رحلة مباشرة",
  "standard.nonstop": "بدون توقف",
  "standard.stops_one": "توقف واحد",
  "standard.stops_other": "عدد محطات التوقف: {count}",

  "matrix.title": "مصفوفة مقارنة الأسعار",
  "matrix.subtitle":
    "أرخص سعر لكل وجهة مذكورة على التذكرة ولكل شركة طيران. أي صف أرخص من صف وجهتك هو مدينة يمكنك تجاوز وجهتك إليها بسعر أقل.",
  "matrix.ticketedTo": "الوجهة على التذكرة",
  "matrix.best": "الأفضل",
  "matrix.yourTarget": "وجهتك",

  "modal.versionNote": "الإصدار {version}. علّم على القواعد الحرجة ({count}) للمتابعة.",
  "modal.accept": "أفهم المخاطر",
  "modal.close": "إغلاق",

  "empty.intro":
    "أدخل موقعك الحالي والوجهة التي تريدها فعلاً. نُسعّر الرحلة المباشرة، ثم نُسعّر الرحلات التي تكمل إلى ما بعد وجهتك، ونُظهر لك متى تكون الرحلة الأطول أرخص.",

  "footer.meta": "المزوّد: {provider} · تم تسعير {probes} سوقاً خلال {ms} مللي ثانية · {time}",

  "error.generic": "حدث خطأ ما.",
  "error.unreachable": "تعذّر الوصول إلى الخادم. هل الخادم الخلفي يعمل؟",
  "error.stream": "انقطع الاتصال ببث نتائج البحث.",

  "theme.toDark": "التبديل إلى المظهر الداكن",
  "theme.toLight": "التبديل إلى المظهر الفاتح",

  "nav.search": "البحث",
  "nav.results": "النتائج",
  "nav.rules": "القواعد والمخاطر",
  "nav.newSearch": "بحث جديد",
  "nav.backToResults": "العودة إلى النتائج",

  "rules.loading": "جارٍ تحميل القواعد…",
  "rules.version": "الإصدار {version}. هذه القواعد مرقّمة بإصدار، وإذا تغيّرت سيُطلب منك قراءتها من جديد.",
  "rules.howTitle": "كيف يعمل سعر الوجهة المخفية",
  "rules.howBody":
    "تُسعّر شركات الطيران الرحلة بحسب المدينة التي تنتهي إليها التذكرة، لا بحسب المسافة التي تقطعها بك الطائرة. لذلك قد تكون تكلفة السفر إلى مطار ربط تهيمن عليه شركة واحدة أعلى من تكلفة السفر إلى مدينة أصغر تقع خلفه. فتشتري التذكرة إلى المدينة الأبعد، وتستقل الرحلة الأولى، ثم تخرج ببساطة عند محطة التوقف، وهي المدينة التي أردتها فعلاً.",
  "rules.diagramNote": "احجز إلى SKP، وانزل في IST، ولا تستقل الرحلة الثانية",
  "rules.group.critical": "الخطأ في هذه يكلّفك",
  "rules.group.warning": "افهم هذه قبل أن تحجز",
  "rules.group.info": "من المفيد معرفته",
  "rules.mustAccept": "يجب الإقرار بها قبل عرض النتائج",
  "rules.checklistTitle": "قبل أن تحجز، تحقّق من الخمس جميعها",
  "rules.checklist.one": "التذكرة ذهاب فقط. وإن احتجت إلى عودة فاشترها بشكل منفصل.",
  "rules.checklist.two": "كل ما ستأخذه معك يتسع في المقصورة.",
  "rules.checklist.three": "جواز سفرك يسمح لك بدخول المدينة التي ستنزل فيها.",
  "rules.checklist.four": "رقم المسافر الدائم غير مضاف إلى الحجز.",
  "rules.checklist.five": "المدينة التي تريدها هي أول محطة هبوط، أو أنك تقبل خطر تحويل المسار.",
  "rules.acceptAll": "قرأت كل ذلك وفهمته",
  "rules.alreadyAccepted": "لقد قبلت هذه القواعد",
  "rules.back": "العودة",
};

export const CATALOGS: Record<Lang, Record<StringKey, string>> = { en, ar };
