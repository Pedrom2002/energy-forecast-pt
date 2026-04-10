"""Map 4-digit Portuguese postal codes to NUTS-II regions.

The 4-digit prefix structure of Portuguese postal codes correlates strongly
with geographic regions. This module provides a mapping from CP4 ranges to
the 5 continental NUTS-II regions used by the energy forecasting model:

    - Norte    (NUTS-II PT11)
    - Centro   (NUTS-II PT16)
    - Lisboa   (NUTS-II PT17, Área Metropolitana de Lisboa)
    - Alentejo (NUTS-II PT18)
    - Algarve  (NUTS-II PT15)

The mapping uses the official CTT/CP4 prefix structure with **3-digit
precision for ambiguous ranges** (notably the 2xxx block, which mixes
Lisboa AML with the Santarém district in Centro). Madeira (90xx) and
Açores (95xx) are excluded as they are not in continental NUTS-II.

References:
- CTT postal code structure: https://www.ctt.pt/feapl_2/app/restricted/postalCodeSearch/postalCodeSearch.jspx
- INE NUTS-II classification: https://www.ine.pt/
"""

from __future__ import annotations

# Postal code prefix → NUTS-II region.
# Each entry is (start_prefix_inclusive, end_prefix_inclusive, region).
# Ranges are processed in order; first match wins.
#
# This list uses 3-digit precision for the ambiguous 2xxx and 6xxx blocks
# and broad 1-digit precision for unambiguous ranges (3xxx, 4xxx, 5xxx,
# 7xxx, 8xxx).
CP4_RANGES: list[tuple[int, int, str]] = [
    # ────────────────────────────────────────────────────────
    # 1xxx — Lisboa city + AML core
    # ────────────────────────────────────────────────────────
    (1000, 1999, "Lisboa"),
    # ────────────────────────────────────────────────────────
    # 2xxx — Mixed: Lisboa AML + Santarém/Leiria (Centro)
    # ────────────────────────────────────────────────────────
    (2000, 2099, "Centro"),   # Santarém district
    (2100, 2199, "Lisboa"),   # Coruche, Loures fringe → AML border (mostly Lisboa)
    (2200, 2399, "Centro"),   # Abrantes, Tomar (Santarém) → Centro
    (2400, 2499, "Centro"),   # Leiria district
    (2500, 2599, "Centro"),   # Caldas da Rainha, Bombarral, Óbidos → Centro (Oeste)
    (2600, 2699, "Lisboa"),   # Vila Franca de Xira, Mafra → AML
    (2700, 2799, "Lisboa"),   # Amadora, Sintra, Cascais → AML
    (2800, 2899, "Lisboa"),   # Almada, Setúbal-Norte → AML
    (2900, 2999, "Lisboa"),   # Setúbal city, Palmela, Sesimbra → AML
    # ────────────────────────────────────────────────────────
    # 3xxx — Centro (Aveiro, Coimbra, Leiria-Norte, Viseu, Guarda-Sul)
    # ────────────────────────────────────────────────────────
    (3000, 3999, "Centro"),
    # ────────────────────────────────────────────────────────
    # 4xxx — Norte (Porto, Braga, Viana do Castelo)
    # ────────────────────────────────────────────────────────
    (4000, 4999, "Norte"),
    # ────────────────────────────────────────────────────────
    # 5xxx — Norte (Vila Real, Bragança, north of Viseu/Guarda)
    # ────────────────────────────────────────────────────────
    (5000, 5999, "Norte"),
    # ────────────────────────────────────────────────────────
    # 6xxx — Centro (Castelo Branco, Guarda-Centro, Covilhã)
    # ────────────────────────────────────────────────────────
    (6000, 6999, "Centro"),
    # ────────────────────────────────────────────────────────
    # 7xxx — Alentejo (Portalegre, Évora, Beja)
    # ────────────────────────────────────────────────────────
    (7000, 7999, "Alentejo"),
    # ────────────────────────────────────────────────────────
    # 8xxx — Algarve (Faro)
    # ────────────────────────────────────────────────────────
    (8000, 8999, "Algarve"),
    # ────────────────────────────────────────────────────────
    # 9xxx — Madeira (90xx) and Açores (95xx) — excluded (NUTS-II PT20/PT30)
    # ────────────────────────────────────────────────────────
]


def cp4_to_region(cp4: str | int) -> str | None:
    """Map a 4-digit postal code to a NUTS-II region name.

    Args:
        cp4: Postal code as string or int. Strings are zero-padded.

    Returns:
        Region name (one of Norte, Centro, Lisboa, Alentejo, Algarve)
        or None if outside continental Portugal (Madeira, Açores) or
        invalid input.
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
    from collections import Counter

    lookup = build_lookup_table()
    counts = Counter(lookup.values())
    print(f"Total CP4 mapped: {len(lookup)}")
    print("By region:")
    for region, n in sorted(counts.items()):
        print(f"  {region:10s}: {n:5d} prefixes")

    # Spot checks
    print("\nSpot checks:")
    test_cases = [
        # (cp4, expected, description)
        ("1100", "Lisboa", "Lisboa city centre"),
        ("1495", "Lisboa", "Algés (AML)"),
        ("2000", "Centro", "Santarém district"),
        ("2070", "Centro", "Cartaxo (Santarém)"),
        ("2100", "Lisboa", "Coruche border / Loures fringe"),
        ("2300", "Centro", "Tomar (Santarém)"),
        ("2400", "Centro", "Leiria"),
        ("2500", "Centro", "Caldas da Rainha"),
        ("2600", "Lisboa", "Vila Franca de Xira"),
        ("2750", "Lisboa", "Cascais"),
        ("2800", "Lisboa", "Almada"),
        ("2900", "Lisboa", "Setúbal city"),
        ("3000", "Centro", "Coimbra"),
        ("3700", "Centro", "São João da Madeira"),
        ("4000", "Norte", "Porto"),
        ("4700", "Norte", "Braga"),
        ("4900", "Norte", "Viana do Castelo"),
        ("5000", "Norte", "Vila Real"),
        ("5300", "Norte", "Bragança"),
        ("6000", "Centro", "Castelo Branco"),
        ("6300", "Centro", "Guarda"),
        ("7000", "Alentejo", "Evora"),
        ("7300", "Alentejo", "Portalegre"),
        ("7800", "Alentejo", "Beja"),
        ("8000", "Algarve", "Faro"),
        ("8500", "Algarve", "Portimao"),
        ("9000", None, "Madeira (excluded)"),
        ("9500", None, "Acores (excluded)"),
    ]
    n_pass = 0
    for cp4, expected, desc in test_cases:
        got = cp4_to_region(cp4)
        ok = got == expected
        n_pass += int(ok)
        status = "OK  " if ok else "FAIL"
        got_str = str(got) if got is not None else "None"
        exp_str = str(expected) if expected is not None else "None"
        print(f"  [{status}] {cp4} -> {got_str:10s} (expected {exp_str:10s}) -- {desc}")
    print(f"\n{n_pass}/{len(test_cases)} spot checks passed")
