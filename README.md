def __init__(self, api_key=None, account_id=None):
    self.api_key     = api_key or os.environ.get("OANDA_API_KEY", "")
    self.account_id  = account_id or os.environ.get("OANDA_ACCOUNT_ID", "")
    self.simulator   = PriceSimulator()
    self.headers     = {}  # always initialise headers

    if self.api_key and HAS_REQUESTS:
        self.live = True
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }
    else:
        self.live = False
        print("[APEX] No API key found — running in simulation mode")





def get_city_name(cert_owner):

    if not isinstance(cert_owner, str) or not cert_owner.strip():
        return None

    exempt_words = ["ltd.", "ltd", "s.i.u",
                    "s.a.", "s.a", "s.r.o.",
                    "s.r.o", "s.i.", "s.i",
                    "s.p.a", "s.p.a.", "s.l.u",
                    "s.l.u", "a.s", "a.s.",
                    "s.l", "s.l.", "inc.", "inc",
                    ". ltd", "-", "oils", "l.p.",
                    "llc", "l.l.c.", "llc.", "lp", "inc.."]

    all_parts = [p.strip() for p in cert_owner.split(",") if p.strip()]

    # Extract country correctly — always the LAST part
    country = all_parts[-1].strip().lower() if all_parts else ""

    # Middle parts only (drop company and country)
    parts = [p.lower() for p in all_parts[1:-1]]

    tokens = [
        tok
        for tok in parts
        if tok
        and tok not in exempt_words
        and not any(w in CITY_STOPWORDS for w in tok.split())
        and not every_word_has_digit(tok)
        and not (len(tok) == 2 and tok.isupper())  # drop US state codes like TX, IL, CA
    ]

    if len(tokens) == 1:
        return " ".join([w for w in tokens[0].split() if not w.isnumeric()]).title()
    elif len(tokens) >= 2:
        if country in ("united states", "china"):
            return " ".join([w for w in tokens[-2].split() if not w.isnumeric()]).title()
        else:
            return " ".join([w for w in tokens[-1].split() if not w.isnumeric()]).title()

    return None
