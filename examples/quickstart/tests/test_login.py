from flows.login_flow import login


def test_login_flow():
    result = login("demo_user", "demo_password")
    assert result.authenticated is True
    assert result.destination == "/dashboard"


def test_login_invalid_password():
    result = login("demo_user", "wrong_password")
    assert result.authenticated is False
    assert result.destination == "/login"


def test_login_unknown_user():
    assert login("unknown", "demo_password").authenticated is False
