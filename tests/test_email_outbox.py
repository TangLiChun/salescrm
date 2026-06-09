from app import database


class _Cur:
    def __init__(self, rows=None, one=None, rowcount=0):
        self._rows, self._one = rows or [], one
        self.rowcount = rowcount

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


def test_count_sent_today_without_user_counts_all():
    # The background sender calls this with NO user_id (global rate limit).
    conn = _Conn()
    conn.next_one = {"n": 12}
    assert database.count_sent_emails_today(conn=conn) == 12
    sql, params = conn.execs[-1]
    assert "user_id" not in sql
    assert params == ()


def test_last_sent_email_at_global_and_per_user():
    conn = _Conn()
    conn.next_one = {"t": None}
    assert database.last_sent_email_at(conn=conn) is None
    sql, params = conn.execs[-1]
    assert "user_id" not in sql and params == ()
    # per-user form still filters by user_id
    conn2 = _Conn()
    conn2.next_one = {"t": None}
    database.last_sent_email_at(7, conn=conn2)
    assert conn2.execs[-1][1] == (7,)
    assert "user_id" in conn2.execs[-1][0]


def test_requeue_stale_sending_resets_to_queued():
    conn = _Conn()
    database.requeue_stale_sending_emails(conn=conn)
    nospace = " ".join(e[0] for e in conn.execs).replace(" ", "")
    assert "UPDATEemail_outbox" in nospace
    assert "status='queued'" in nospace
    assert "status='sending'" in nospace
