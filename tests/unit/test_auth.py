from types import SimpleNamespace

from vkr_checker.config import Settings
from vkr_checker.web.auth import Authenticator, LoginRateLimiter


def make_auth(clock, **kw):
    s = Settings(mode="server", password="secret-pw", **kw)
    return Authenticator(s, clock=clock)


def req(cookie=None, bearer=None, ip="1.1.1.1", xff=None):
    headers = {}
    if bearer:
        headers["authorization"] = f"Bearer {bearer}"
    if xff:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(
        cookies={"vkr_session": cookie} if cookie else {},
        headers=headers,
        client=SimpleNamespace(host=ip),
    )


def test_token_roundtrip_and_expiry():
    now = [1000.0]
    a = make_auth(lambda: now[0], session_ttl_h=1)
    token = a.issue_token()
    assert a.verify_token(token)
    now[0] += 3601
    assert not a.verify_token(token)


def test_tampered_token_rejected():
    a = make_auth(lambda: 1000.0)
    exp, sig = a.issue_token().split(".")
    assert not a.verify_token(f"{int(exp) + 99999}.{sig}")
    assert not a.verify_token(None)
    assert not a.verify_token("garbage")
    assert not a.verify_token("abc.def")


def test_token_invalid_for_other_boot():
    t = make_auth(lambda: 1000.0).issue_token()
    assert not make_auth(lambda: 1000.0).verify_token(t)


def test_bearer_and_cookie():
    a = make_auth(lambda: 1000.0)
    assert not a.is_authenticated(req())
    assert a.is_authenticated(req(bearer="secret-pw"))
    assert not a.is_authenticated(req(bearer="wrong"))
    assert a.is_authenticated(req(cookie=a.issue_token()))


def test_local_mode_open():
    a = Authenticator(Settings(mode="local"))
    assert a.is_authenticated(req())


def test_rate_limiter_blocks_and_expires():
    now = [0.0]
    lim = LoginRateLimiter(2, clock=lambda: now[0])
    assert lim.retry_after("ip") is None
    lim.register_failure("ip")
    lim.register_failure("ip")
    assert lim.retry_after("ip") >= 1
    assert lim.retry_after("other") is None
    now[0] = 61
    assert lim.retry_after("ip") is None


def test_client_ip_proxy():
    a = make_auth(lambda: 0.0, trust_proxy=True)
    assert a.client_ip(req(xff="9.9.9.9, 2.2.2.2")) == "2.2.2.2"
    b = make_auth(lambda: 0.0)
    assert b.client_ip(req(xff="9.9.9.9")) == "1.1.1.1"


def test_wrong_bearer_counts_as_failed_attempt_and_blocks():
    import pytest

    from vkr_checker.web.errors import ApiError

    a = make_auth(lambda: 0.0, login_rate_per_min=3)
    for _ in range(3):
        assert not a.is_authenticated(req(bearer="bad"))
    with pytest.raises(ApiError):
        a.is_authenticated(req(bearer="secret-pw"))


def test_valid_bearer_resets_counter():
    a = make_auth(lambda: 0.0, login_rate_per_min=3)
    assert not a.is_authenticated(req(bearer="bad"))
    assert a.is_authenticated(req(bearer="secret-pw"))
    assert a.limiter.retry_after("1.1.1.1") is None


def test_session_check_ignores_bearer():
    a = make_auth(lambda: 0.0)
    assert not a.has_valid_session(req(bearer="secret-pw"))
    assert a.has_valid_session(req(cookie=a.issue_token()))


def test_limiter_sweeps_stale_ips():
    now = [0.0]
    lim = LoginRateLimiter(5, clock=lambda: now[0])
    for i in range(50):
        lim.register_failure(f"10.0.0.{i}")
    now[0] += 120
    lim.register_failure("9.9.9.9")
    assert list(lim._fails) == ["9.9.9.9"]
