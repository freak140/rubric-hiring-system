from app.services.auth import hash_password, sign_session, verify_password, verify_session


def test_hash_password_round_trips():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong password", stored)


def test_hash_password_uses_a_fresh_salt_each_time():
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b  # different random salts
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_verify_password_rejects_missing_or_malformed_hash():
    assert not verify_password("anything", None)
    assert not verify_password("anything", "")
    assert not verify_password("anything", "not-a-valid-hash-format")


def test_session_round_trips():
    token = sign_session(42)
    assert verify_session(token) == 42


def test_session_rejects_tampered_payload():
    token = sign_session(42)
    payload, _, signature = token.partition(".")
    tampered = f"43.{signature}"  # changed the user id, kept the old signature
    assert verify_session(tampered) is None


def test_session_rejects_garbage():
    assert verify_session(None) is None
    assert verify_session("") is None
    assert verify_session("not-a-valid-session-token") is None
