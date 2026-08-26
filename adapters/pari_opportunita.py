from __future__ import annotations

import re
from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, parse_listing_records


class PariOpportunitaAdapter(DedicatedHtmlAdapter):
    source_id = "pari_opportunita"
    # The old category route now returns 404.  The official tag-search page
    # is the server-rendered replacement and keeps the ``Bandi e Avvisi``
    # filter without requiring browser automation.
    page_url = "https://www.pariopportunita.gov.it/it/tagsearch/?id=38a755cc-0701-4934-8d9c-71fb0310febc"
    source_label = "Dipartimento per le pari opportunità"
    funder = "Dipartimento per le pari opportunità"
    programme = "Bandi e avvisi per pari opportunità, inclusione e contrasto alla violenza"
    url_tokens = ("bando", "avviso", "manifestaz", "coprogett", "finanziament")
    # The replacement listing itself lives under ``/news-e-media/news``;
    # exclude editorial/result markers in the title or detail slug instead of
    # rejecting the entire official listing path.
    excluded_tokens = ("faq", "graduatori", "esiti", "eventi", "premi", "comunicat", "incaric", "esperti", "linee-guida", "aggiornament")
    allow_status_context = True

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        records = parse_listing_records(self, raw, allow_status_context=True)
        # A detail page can expose an administrative heading before the real
        # call; never let those headings become records.
        return [record for record in records if not re.search(r"\b(?:premio|graduatori|esit|evento)\b", record.title, re.I)]
