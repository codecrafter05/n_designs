"""Best-effort country-name → calling-code lookup for the phone dial <select>.

This is not the shippable-country list. Storefront destinations come from
DeliveryGroupCountry. These names only resolve a prefix/flag when the
merchant-typed country matches (or an alias of) a known English name.
"""

from __future__ import annotations

# English name (as commonly typed) → (dial with +, flag).
_OFFICIAL: dict[str, tuple[str, str]] = {
    "Afghanistan": ("+93", "🇦🇫"),
    "Albania": ("+355", "🇦🇱"),
    "Algeria": ("+213", "🇩🇿"),
    "Argentina": ("+54", "🇦🇷"),
    "Armenia": ("+374", "🇦🇲"),
    "Australia": ("+61", "🇦🇺"),
    "Austria": ("+43", "🇦🇹"),
    "Azerbaijan": ("+994", "🇦🇿"),
    "Bahrain": ("+973", "🇧🇭"),
    "Bangladesh": ("+880", "🇧🇩"),
    "Belarus": ("+375", "🇧🇾"),
    "Belgium": ("+32", "🇧🇪"),
    "Bosnia and Herzegovina": ("+387", "🇧🇦"),
    "Brazil": ("+55", "🇧🇷"),
    "Brunei": ("+673", "🇧🇳"),
    "Bulgaria": ("+359", "🇧🇬"),
    "Cambodia": ("+855", "🇰🇭"),
    "Canada": ("+1", "🇨🇦"),
    "Chile": ("+56", "🇨🇱"),
    "China": ("+86", "🇨🇳"),
    "Colombia": ("+57", "🇨🇴"),
    "Croatia": ("+385", "🇭🇷"),
    "Cyprus": ("+357", "🇨🇾"),
    "Czech Republic": ("+420", "🇨🇿"),
    "Denmark": ("+45", "🇩🇰"),
    "Egypt": ("+20", "🇪🇬"),
    "Estonia": ("+372", "🇪🇪"),
    "Ethiopia": ("+251", "🇪🇹"),
    "Finland": ("+358", "🇫🇮"),
    "France": ("+33", "🇫🇷"),
    "Georgia": ("+995", "🇬🇪"),
    "Germany": ("+49", "🇩🇪"),
    "Ghana": ("+233", "🇬🇭"),
    "Greece": ("+30", "🇬🇷"),
    "Hong Kong": ("+852", "🇭🇰"),
    "Hungary": ("+36", "🇭🇺"),
    "Iceland": ("+354", "🇮🇸"),
    "India": ("+91", "🇮🇳"),
    "Indonesia": ("+62", "🇮🇩"),
    "Iran": ("+98", "🇮🇷"),
    "Iraq": ("+964", "🇮🇶"),
    "Ireland": ("+353", "🇮🇪"),
    "Israel": ("+972", "🇮🇱"),
    "Italy": ("+39", "🇮🇹"),
    "Japan": ("+81", "🇯🇵"),
    "Jordan": ("+962", "🇯🇴"),
    "Kazakhstan": ("+7", "🇰🇿"),
    "Kenya": ("+254", "🇰🇪"),
    "Kuwait": ("+965", "🇰🇼"),
    "Latvia": ("+371", "🇱🇻"),
    "Lebanon": ("+961", "🇱🇧"),
    "Libya": ("+218", "🇱🇾"),
    "Lithuania": ("+370", "🇱🇹"),
    "Luxembourg": ("+352", "🇱🇺"),
    "Macau": ("+853", "🇲🇴"),
    "Malaysia": ("+60", "🇲🇾"),
    "Maldives": ("+960", "🇲🇻"),
    "Malta": ("+356", "🇲🇹"),
    "Mexico": ("+52", "🇲🇽"),
    "Morocco": ("+212", "🇲🇦"),
    "Nepal": ("+977", "🇳🇵"),
    "Netherlands": ("+31", "🇳🇱"),
    "New Zealand": ("+64", "🇳🇿"),
    "Nigeria": ("+234", "🇳🇬"),
    "Norway": ("+47", "🇳🇴"),
    "Oman": ("+968", "🇴🇲"),
    "Pakistan": ("+92", "🇵🇰"),
    "Palestine": ("+970", "🇵🇸"),
    "Philippines": ("+63", "🇵🇭"),
    "Poland": ("+48", "🇵🇱"),
    "Portugal": ("+351", "🇵🇹"),
    "Qatar": ("+974", "🇶🇦"),
    "Romania": ("+40", "🇷🇴"),
    "Russia": ("+7", "🇷🇺"),
    "Saudi Arabia": ("+966", "🇸🇦"),
    "Serbia": ("+381", "🇷🇸"),
    "Singapore": ("+65", "🇸🇬"),
    "Slovakia": ("+421", "🇸🇰"),
    "Slovenia": ("+386", "🇸🇮"),
    "South Africa": ("+27", "🇿🇦"),
    "South Korea": ("+82", "🇰🇷"),
    "Spain": ("+34", "🇪🇸"),
    "Sri Lanka": ("+94", "🇱🇰"),
    "Sudan": ("+249", "🇸🇩"),
    "Sweden": ("+46", "🇸🇪"),
    "Switzerland": ("+41", "🇨🇭"),
    "Syria": ("+963", "🇸🇾"),
    "Taiwan": ("+886", "🇹🇼"),
    "Thailand": ("+66", "🇹🇭"),
    "Tunisia": ("+216", "🇹🇳"),
    "Turkey": ("+90", "🇹🇷"),
    "Ukraine": ("+380", "🇺🇦"),
    "United Arab Emirates": ("+971", "🇦🇪"),
    "United Kingdom": ("+44", "🇬🇧"),
    "United States": ("+1", "🇺🇸"),
    "Vietnam": ("+84", "🇻🇳"),
    "Yemen": ("+967", "🇾🇪"),
}

# Lowercase aliases → official key in _OFFICIAL.
_ALIASES: dict[str, str] = {
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "united states of america": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "ksa": "Saudi Arabia",
    "saudi": "Saudi Arabia",
    "kingdom of saudi arabia": "Saudi Arabia",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "czechia": "Czech Republic",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
}


def _index() -> dict[str, tuple[str, str]]:
    table: dict[str, tuple[str, str]] = {}
    for name, pair in _OFFICIAL.items():
        table[name.lower()] = pair
    for alias, official in _ALIASES.items():
        pair = _OFFICIAL.get(official)
        if pair is not None:
            table[alias.lower()] = pair
    return table


_INDEX = _index()


def lookup_dial(country_name: str) -> tuple[str, str] | None:
    key = (country_name or "").strip().lower()
    if not key:
        return None
    return _INDEX.get(key)


def dial_prefixes() -> tuple[str, ...]:
    """Digit prefixes, longest first, for parsing stored +code numbers."""
    codes = {pair[0].lstrip("+") for pair in _OFFICIAL.values()}
    return tuple(sorted(codes, key=lambda c: (-len(c), c)))
