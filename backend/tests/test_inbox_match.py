"""BUG 3: a reply from a DIFFERENT address than received must still match via the
In-Reply-To / References header (Message-ID), not be silently dropped."""
import email

from app.workers.inbox import match_inbound


class _Msg:
    """Stand-in EmailMessage with the stamped Message-ID."""
    def __init__(self, mid, to):
        self.meta = {"message_id": mid, "to": to}


def _inbound(from_addr, in_reply_to=None):
    raw = f"From: {from_addr}\r\nSubject: Re: Quick question\r\n"
    if in_reply_to:
        raw += f"In-Reply-To: {in_reply_to}\r\n"
    raw += "\r\nYes, interested!"
    return email.message_from_string(raw)


def test_primary_sender_match():
    sent = _Msg("<abc@leadforge.ai>", "prospect@acme.com")
    sender_index = {"prospect@acme.com": sent}
    mid_index = {"<abc@leadforge.ai>": sent}
    match, how = _inbound_match(sender_index, mid_index,
                                _inbound("Prospect <prospect@acme.com>"))
    assert match is sent and how == "sender"


def test_secondary_header_match_when_from_differs():
    # We sent to prospect@acme.com; the human replies from john.doe@gmail.com.
    sent = _Msg("<stamped-id-123@leadforge.ai>", "prospect@acme.com")
    sender_index = {"prospect@acme.com": sent}
    mid_index = {"<stamped-id-123@leadforge.ai>": sent}
    reply = _inbound("John Doe <john.doe@gmail.com>",
                     in_reply_to="<stamped-id-123@leadforge.ai>")
    match, how = match_inbound(reply, sender_index, mid_index)
    assert match is sent, "secondary header match must fire"
    assert how == "header"


def test_truly_unmatched_returns_none():
    sent = _Msg("<x@leadforge.ai>", "prospect@acme.com")
    reply = _inbound("stranger@nowhere.com", in_reply_to="<unrelated@x.com>")
    match, how = match_inbound(reply, {"prospect@acme.com": sent}, {"<x@leadforge.ai>": sent})
    assert match is None and how == "none"


def _inbound_match(sender_index, mid_index, msg):
    return match_inbound(msg, sender_index, mid_index)
