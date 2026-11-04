"""Shared credentials for the platform API tests. Not a pytest plugin."""

OPERATOR_EMAIL = "operator@example.com"
OPERATOR_PASSWORD = "operator-pass"
ALPHA_ADMIN_EMAIL = "alpha-admin@example.com"
ALPHA_ADMIN_PASSWORD = "alpha-admin-pass"
BETA_ADMIN_EMAIL = "beta-admin@example.com"
BETA_ADMIN_PASSWORD = "beta-admin-pass"
AUDITOR_EMAIL = "alpha-auditor@example.com"
AUDITOR_PASSWORD = "alpha-auditor-pass"


def login(client, email: str, password: str):
    client.cookies.clear()
    response = client.post(
        "/platform/v1/session",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response
