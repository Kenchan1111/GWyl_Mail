from email.message import EmailMessage

from gwyl_mail.canonical import GWylCanonical


def test_simple_message_hash_stable():
    msg = EmailMessage()
    msg["From"] = "alice@company.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Hello"
    msg["Date"] = "Thu, 11 Jan 2025 14:30:22 +0000"
    msg["Message-ID"] = "<test1@company.com>"
    msg.set_content("Hello Bob!")

    h1 = GWylCanonical.hash(msg)
    h2 = GWylCanonical.hash(msg)
    assert h1 == h2


def test_headers_added_are_ignored():
    msg1 = EmailMessage()
    msg1["From"] = "alice@company.com"
    msg1["To"] = "bob@example.com"
    msg1["Subject"] = "Test"
    msg1["Date"] = "Thu, 11 Jan 2025 14:30:22 +0000"
    msg1["Message-ID"] = "<test@company.com>"
    msg1.set_content("Body")

    msg2 = EmailMessage()
    msg2["Received"] = "from mail.google.com"
    msg2["X-Spam"] = "No"
    msg2["From"] = "alice@company.com"
    msg2["To"] = "bob@example.com"
    msg2["Subject"] = "Test"
    msg2["Date"] = "Thu, 11 Jan 2025 14:30:22 +0000"
    msg2["Message-ID"] = "<test@company.com>"
    msg2.set_content("Body")

    assert GWylCanonical.hash(msg1) == GWylCanonical.hash(msg2)

