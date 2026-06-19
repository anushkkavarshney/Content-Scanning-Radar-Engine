from services.normalizer import validate_real_estate_article


def mk(t,d='',c='',s='test'):
    return {'title':t,'description':d,'content':c,'source':s}


def test_sports_rejected():
    r = validate_real_estate_article(mk('Chelsea sign new striker'))
    assert not r['accepted']

def test_crypto_rejected():
    r = validate_real_estate_article(mk('Bitcoin hits new high'))
    assert not r['accepted']

def test_gambling_rejected():
    r = validate_real_estate_article(mk('Free spins casino offers'))
    assert not r['accepted']

def test_healthcare_rejected():
    r = validate_real_estate_article(mk('Hospital admits new patients'))
    assert not r['accepted']

def test_real_estate_accepted():
    r = validate_real_estate_article(mk('California home sales rise', d='Housing market shows strength', c='mortgage and home sales'))
    assert r['accepted']
