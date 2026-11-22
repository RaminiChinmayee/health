"""Test setup: a dedicated PostgreSQL database and a real local SMTP server.

Set TEST_DATABASE_URL to point at an empty database (default: healthai_test).
"""
import os
import re
import socket
from email import message_from_bytes, policy

import pytest

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://healthai@127.0.0.1:54329/healthai_test"
)
os.environ["EMAIL_BACKEND"] = "smtp"
os.environ["SMTP_HOST"] = "127.0.0.1"
os.environ["SMTP_USE_TLS"] = "false"
os.environ["SMTP_USERNAME"] = ""
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-0123456789"
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


SMTP_PORT = _free_port()
os.environ["SMTP_PORT"] = str(SMTP_PORT)

from aiosmtpd.controller import Controller  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


class Mailbox:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        msg = message_from_bytes(envelope.content, policy=policy.default)
        self.messages.append({"to": envelope.rcpt_tos, "subject": msg["subject"], "text": msg.get_body(("plain",)).get_content()})
        return "250 OK"

    def last_link(self, to: str, path: str) -> str:
        for m in reversed(self.messages):
            if to in m["to"]:
                found = re.search(rf"{re.escape(path)}\?token=([\w-]+)", m["text"])
                if found:
                    return found.group(1)
        raise AssertionError(f"no {path} email for {to}: {self.messages}")


@pytest.fixture(scope="session")
def mailbox():
    box = Mailbox()
    ctl = Controller(box, hostname="127.0.0.1", port=SMTP_PORT)
    ctl.start()
    yield box
    ctl.stop()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    assert "test" in get_settings().database_url, "refusing to run tests against a non-test database"
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean(mailbox, tmp_path, monkeypatch):
    with engine.begin() as c:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {tables} CASCADE"))
    mailbox.messages.clear()
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    yield


@pytest.fixture
def client():
    return TestClient(app)


STRONG = "Correct-Horse-42-battery"


def register(client, email="asha@example.com", password=STRONG, **kw):
    body = {
        "full_name": "Asha Rao",
        "email": email,
        "password": password,
        "confirm_password": password,
        "date_of_birth": "1995-04-12",
        "gender": "female",
        "accept_terms": True,
        "language": "te",
        **kw,
    }
    return client.post("/api/auth/register", json=body)


def verified_login(client, mailbox, email="asha@example.com", remember=False):
    assert register(client, email=email).status_code == 201
    token = mailbox.last_link(email, "/verify-email")
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    r = client.post("/api/auth/login", json={"email": email, "password": STRONG, "remember_me": remember})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


CSRF = {"X-HealthAI-CSRF": "1"}
