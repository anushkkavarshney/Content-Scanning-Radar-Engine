from services.normalizer import is_real_estate_article

tests = [
    ("California Home Sales Rise From Year-Ago", True),
    ("Multifamily starts crater 41.6%", True),
    ("FHFA pushes for direct power to sue for mortgage fraud", True),
    ("Lewis Hall: Chelsea threaten Man United", False),
    ("Free Spins Casinos 2026", False),
    ("Crescom Launches Pediatric Musculoskeletal AI", False),
    ("Better prompts won't fix your workslop problem", False)
]

failed = []
for title, expected in tests:
    res = is_real_estate_article({"title": title, "description": "", "content": "", "source": "test"})
    print(f"Test: {title!r} -> expected={expected} got={res}")
    if res != expected:
        failed.append((title, expected, res))

print('\nRESULTS: total=', len(tests), 'failed=', len(failed))
if failed:
    for f in failed:
        print('FAIL:', f)
    raise SystemExit(2)
else:
    print('All tests passed')
