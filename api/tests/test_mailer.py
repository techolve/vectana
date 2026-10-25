from app.core.config import settings
from app.services.mailer import build_message


def test_message_has_required_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "mail_from", "Vectana <no-reply@techolve.org>")
    msg = build_message("a@example.com", "[Vectana] テスト", "本文", "<p>本文</p>")
    assert msg["Date"]
    assert msg["Message-ID"].endswith("@techolve.org>")
    assert msg["From"] == "Vectana <no-reply@techolve.org>"
    assert msg.is_multipart()
