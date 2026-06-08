from app import database


class _Cur:
    def __init__(self, rows=None, one=None):
        self._rows, self._one = rows or [], one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _Conn:
    def __init__(self):
        self.execs = []
        self.next_one = None
        self.next_all = []

    def execute(self, sql, params=None):
        self.execs.append((" ".join(sql.split()), params))
        verb = " ".join(sql.split()).upper()
        if "RETURNING" in verb or verb.startswith("SELECT"):
            return _Cur(rows=self.next_all, one=self.next_one)
        return _Cur()


def test_count_sent_today_uses_user_and_date(monkeypatch):
    conn = _Conn()
    conn.next_one = {"n": 7}
    assert database.count_sent_emails_today(1, conn=conn) == 7
    assert any(
        "status = 'sent'" in e[0] or "status='sent'" in e[0].replace(" ", "") for e in conn.execs
    )


def test_claim_next_queued_marks_sending(monkeypatch):
    conn = _Conn()
    conn.next_one = {
        "id": 5,
        "to_email": "x@y.com",
        "subject": "s",
        "body_text": "t",
        "body_html": "",
        "contact_id": 9,
        "attempts": 0,
    }
    row = database.claim_next_queued_email(conn=conn)
    assert row["id"] == 5
    joined = " ".join(e[0] for e in conn.execs)
    assert "SKIP LOCKED" in joined and "status = 'sending'" in joined.replace("='", "= '")
