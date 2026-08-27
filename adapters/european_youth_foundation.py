from __future__ import annotations

import re

import funding_core.adapters as _core_adapters
from funding_core.adapters import AdapterError, FetchPolicy
from funding_core.models import SourceRecord

from ._v04_common import clean, dates_in, fetch_bytes, page_text


class EuropeanYouthFoundationAdapter:
    """Parse the Council of Europe EYF calls page by its status sections."""

    source_id = "european_youth_foundation"
    page_url = "https://www.coe.int/en/web/european-youth-foundation/calls"
    fallback_url = "https://www.coe.int/en/web/european-youth-foundation/home"
    source_label = "European Youth Foundation"
    funder = "Council of Europe – European Youth Foundation"
    programme = "EYF calls for proposals"
    max_bytes = 3_000_000
    _call_re = re.compile(r"\bCall for proposals\s+for[^.]{0,320}?\((20\d{2}\.C\d+(?:\.[A-Z])?)\)", re.IGNORECASE)

    def _fetch_one(self, url: str, policy: FetchPolicy) -> bytes:
        return fetch_bytes(url, policy, label=self.source_label)

    def fetch(self, policy: FetchPolicy | None = None) -> bytes:
        policy = policy or FetchPolicy(max_bytes=self.max_bytes)
        try:
            return self._fetch_one(self.page_url, policy)
        except AdapterError as exc:
            # The Council of Europe occasionally returns a short-lived 403 for
            # the calls route while the official EYF home page remains public.
            # The fallback is still first-party and carries the open calls.
            if exc.status_code == 403:
                return self._fetch_one(self.fallback_url, policy)
            raise

    @staticmethod
    def _status(prefix: str) -> str:
        matches = list(re.finditer(r"OPEN|CLOSED|CALL TO BE ANNOUNCED(?: IN [A-Z]+)?", prefix, re.IGNORECASE))
        if not matches:
            return "UNKNOWN"
        value = matches[-1].group(0).upper()
        return "OPEN" if value == "OPEN" else "CLOSED" if value == "CLOSED" else "UPCOMING"

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = page_text(raw)
        records: list[SourceRecord] = []
        seen: set[str] = set()
        matches = list(self._call_re.finditer(text))
        for index, match in enumerate(matches):
            code = match.group(1).upper()
            if code in seen:
                continue
            seen.add(code)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            context = text[match.start():end]
            deadline_match = re.search(r"Deadline for submission\s*:\s*([^\.]{1,100})", context, re.IGNORECASE)
            deadline = dates_in(deadline_match.group(1), default_year=int(code[:4]))[-1] if deadline_match and dates_in(deadline_match.group(1), default_year=int(code[:4])) else None
            status = self._status(text[max(0, match.start() - 220):match.start()])
            if status == "UNKNOWN":
                # Pages rendered from a compact home template may place the
                # status after the card heading rather than before it.
                status = self._status(context[:140])
            records.append(SourceRecord(
                external_id=code.lower(),
                title=clean(match.group(0)),
                official_url=self.page_url,
                funder=self.funder,
                programme=self.programme,
                deadline=deadline,
                eligible_entities=("Youth organisations registered with the European Youth Foundation",),
                description=clean(context[:1800]),
                source_status=status,
                status_authoritative=True,
                territory="Council of Europe / internazionale",
            ))
        return records
