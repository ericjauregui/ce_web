from __future__ import annotations

from collections import defaultdict
from typing import Final

import pycountry

CountryOption = tuple[str, str]

DEFAULT_LOCATION_COUNTRY_KEY: Final[str] = "us"
_PREFERRED_LOCATION_COUNTRY_KEYS: Final[tuple[str, ...]] = ("us", "mx")
_COUNTRY_LABEL_OVERRIDES: Final[dict[str, str]] = {
    "bo": "Bolivia",
    "ci": "Cote d'Ivoire",
    "fm": "Micronesia",
    "kr": "South Korea",
    "kp": "North Korea",
    "md": "Moldova",
    "mk": "North Macedonia",
    "ps": "Palestine",
    "ru": "Russia",
    "sy": "Syria",
    "tw": "Taiwan",
    "tz": "Tanzania",
    "ve": "Venezuela",
    "vn": "Vietnam",
}
_EXTRA_COUNTRY_OPTIONS: Final[tuple[CountryOption, ...]] = (("xk", "Kosovo"),)


def _country_label(country: pycountry.db.Country) -> str:
    country_key = country.alpha_2.lower()
    if country_key in _COUNTRY_LABEL_OVERRIDES:
        return _COUNTRY_LABEL_OVERRIDES[country_key]
    return str(getattr(country, "common_name", None) or country.name)


def _build_country_options() -> tuple[CountryOption, ...]:
    countries = [
        (country.alpha_2.lower(), _country_label(country))
        for country in pycountry.countries
        if getattr(country, "alpha_2", None)
    ]
    countries.extend(_EXTRA_COUNTRY_OPTIONS)

    countries_by_key = {key: (key, label) for key, label in countries}
    preferred = [countries_by_key[key] for key in _PREFERRED_LOCATION_COUNTRY_KEYS if key in countries_by_key]
    preferred_keys = {key for key, _ in preferred}
    remaining = sorted(
        (option for option in countries_by_key.values() if option[0] not in preferred_keys),
        key=lambda option: option[1],
    )
    return tuple([*preferred, *remaining])


def _build_subdivision_options() -> dict[str, tuple[str, ...]]:
    subdivisions_by_country: defaultdict[str, set[str]] = defaultdict(set)
    for subdivision in pycountry.subdivisions:
        country_code = (getattr(subdivision, "country_code", "") or "").strip().lower()
        subdivision_name = (getattr(subdivision, "name", "") or "").strip()
        if not country_code or not subdivision_name:
            continue
        parent_code = (getattr(subdivision, "parent_code", "") or "").strip()
        if parent_code:
            continue
        subdivisions_by_country[country_code].add(subdivision_name)

    return {
        country_key: tuple(sorted(names))
        for country_key, names in subdivisions_by_country.items()
    }


CHECKOUT_COUNTRY_OPTIONS: Final[tuple[CountryOption, ...]] = _build_country_options()
CHECKOUT_COUNTRY_LABELS_BY_KEY: Final[dict[str, str]] = {key: label for key, label in CHECKOUT_COUNTRY_OPTIONS}
CHECKOUT_COUNTRY_KEY_BY_LABEL: Final[dict[str, str]] = {
    label.casefold(): key for key, label in CHECKOUT_COUNTRY_OPTIONS
}
CHECKOUT_SUBDIVISION_OPTIONS_BY_COUNTRY_KEY: Final[dict[str, tuple[str, ...]]] = _build_subdivision_options()


def get_location_country_option(country_key: str | None) -> CountryOption:
    normalized_key = (country_key or "").strip().lower()
    if normalized_key in CHECKOUT_COUNTRY_LABELS_BY_KEY:
        return normalized_key, CHECKOUT_COUNTRY_LABELS_BY_KEY[normalized_key]
    return DEFAULT_LOCATION_COUNTRY_KEY, CHECKOUT_COUNTRY_LABELS_BY_KEY[DEFAULT_LOCATION_COUNTRY_KEY]


def get_location_country_key_from_label(country_label: str | None) -> str:
    return CHECKOUT_COUNTRY_KEY_BY_LABEL.get((country_label or "").strip().casefold(), "")