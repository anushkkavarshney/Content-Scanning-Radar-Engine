import pytest
from services.normalizer import is_real_estate_article


def make_article(title, description="", content="", source="test"):
    return {"title": title, "description": description, "content": content, "source": source}


def test_accept_examples():
    assert is_real_estate_article(make_article('California Home Sales Rise From Year-Ago'))
    assert is_real_estate_article(make_article('Multifamily starts crater 41.6%'))
    assert is_real_estate_article(make_article('FHFA pushes for direct power to sue for mortgage fraud'))


def test_reject_examples():
    assert not is_real_estate_article(make_article('Lewis Hall: Chelsea threaten Man United'))
    assert not is_real_estate_article(make_article('Free Spins Casinos 2026'))
    assert not is_real_estate_article(make_article('Crescom Launches Pediatric Musculoskeletal AI'))
    assert not is_real_estate_article(make_article("Better prompts won't fix your workslop problem"))
