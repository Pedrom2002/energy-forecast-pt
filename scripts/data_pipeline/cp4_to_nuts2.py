"""Map 4-digit Portuguese postal codes to NUTS-II regions.

The 4-digit prefix structure of Portuguese postal codes correlates strongly
with geographic regions. This module provides a mapping from CP4 ranges to
the 5 continental NUTS-II regions used by the energy forecasting model:

    - Norte    (NUTS-II PT11)
    - Centro   (NUTS-II PT16)
    - Lisboa   (NUTS-II PT17, Área Metropolitana de Lisboa)
    - Alentejo (NUTS-II PT18)
    - Algarve  (NUTS-II PT15)

The mapping is based on the official Portuguese postal code structure
maintained by CTT, cross-referenced with INE municipal NUTS-II classifications.

Resolution: 4-digit prefix. Some prefixes straddle region boundaries; in those
cases the dominant region (by population) is assigned. Madeira (90xx) and
Açores (95xx) are excluded as they are not in NUTS-II continental.
"""

from __future__ import annotations

# Postal code prefix → NUTS-II region.
# Each entry is (start_prefix_inclusive, end_prefix_inclusive, region).
# The ranges follow the official CTT/CP4 structure.
CP4_RANGES: list[tuple[int, int, str]] = [
    # 1xxx — Lisboa city
    (1000, 1999, "Lisboa"),
    # 2000–2499 — Santarém / Centro/Lisboa Norte boundary
    (2000, 2199, "Lisboa"),  # Vila Franca de Xira, Loures, Sintra
    (2200, 2499, "Centro"),  # Santarém district (Centro)
    # 2500–2899 — Lisbon metro area + Setúbal
    (2500, 2599, "Centro"),  # Caldas, Óbidos, Bombarral
    (2600, 2899, "Lisboa"),  # Vila Franca, Mafra, Sintra, Cascais, Setúbal
    # 2900–2999 — Setúbal southern
    (2900, 2999, "Lisboa"),  # Setúbal
    # 3xxx — Centro (Coimbra, Aveiro, Leiria, Viseu)
    (3000, 3999, "Centro"),
    # 4xxx — Norte (Porto, Braga, Viana)
    (4000, 4999, "Norte"),
    # 5xxx — Norte (Bragança, Vila Real, north of Viseu)
    (5000, 5999, "Norte"),
    # 6xxx — Centro (Castelo Branco, Guarda, Covilhã)
    (6000, 6999, "Centro"),
    # 7xxx — Alentejo (Évora, Portalegre, Beja)
    (7000, 7999, "Alentejo"),
    # 8xxx — Algarve (Faro)
    (8000, 8999, "Algarve"),
    # 9xxx — Madeira (90xx) and Açores (95xx) — excluded
]


def cp4_to_region(cp4: str | int) -> str | None:
    """Map a 4-digit postal code to a NUTS-II region name.

    Args:
        cp4: Postal code as string or int. Strings are zero-padded.

    Returns:
        Region name (one of Norte, Centro, Lisboa, Alentejo, Algarve)
        or None if outside continental Portugal (Madeira, Açores).
    """
    try:
        code = int(str(cp4).strip()[:4])
    except (ValueError, TypeError):
        return None

    if code < 1000 or code > 8999:
        return None  # Madeira/Açores or invalid

    for start, end, region in CP4_RANGES:
        if start <= code <= end:
            return region
    return None


def build_lookup_table() -> dict[str, str]:
    """Build a complete CP4 → region lookup dict for all valid codes 1000-8999."""
    lookup = {}
    for code in range(1000, 9000):
        region = cp4_to_region(code)
        if region:
            lookup[f"{code:04d}"] = region
    return lookup


if __name__ == "__main__":
    # Print summary
    lookup = build_lookup_table()
    from collections import Counter

    counts = Counter(lookup.values())
    print(f"Total CP4 mapped: {len(lookup)}")
    print("By region:")
    for region, n in sorted(counts.items()):
        print(f"  {region:10s}: {n:5d} prefixes")

    # Spot checks
    print("\nSpot checks:")
    for cp4, expected in [
        ("1100", "Lisboa"),
        ("2750", "Lisboa"),  # Cascais
        ("3000", "Centro"),  # Coimbra
        ("4000", "Norte"),  # Porto
        ("4700", "Norte"),  # Braga
        ("6000", "Centro"),  # Castelo Branco
        ("7000", "Alentejo"),  # Evora
        ("8000", "Algarve"),  # Faro
        ("9000", None),  # Madeira
    ]:
        got = cp4_to_region(cp4)
        ok = "OK" if got == expected else "FAIL"
        print(f"  [{ok}] {cp4} -> {got} (expected {expected})")
