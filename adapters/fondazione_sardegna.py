from __future__ import annotations

import re

from funding_core.models import SourceRecord

from ._common import DedicatedHtmlAdapter, compact, decode_html


class FondazioneSardegnaAdapter(DedicatedHtmlAdapter):
    source_id = "fondazione_sardegna"
    page_url = "https://www.fondazionedisardegna.it/contributi/bandi-rol"
    source_label = "Fondazione di Sardegna"
    funder = "Fondazione di Sardegna"
    programme = "Bandi annuali 2026 — Fondazione di Sardegna"
    detail_enrichment = False

    _sectors = {
        "arte": "Arte",
        "sviluppo locale": "Sviluppo locale",
        "volontariato": "Volontariato",
        "salute e medicina": "Salute e Medicina",
    }

    def fetch(self, policy=None) -> bytes:
        return super().fetch(policy)

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        records: list[SourceRecord] = []
        for key, label in self._sectors.items():
            if not re.search(rf"{re.escape(key)}", text, re.I):
                continue
            section = re.search(rf"{re.escape(key)}(.{{0,500}}?)(?:Bandi\s+2026|Bando\s+2026)", text, re.I | re.S)
            context = compact(section.group(0) if section else f"{label}: Bandi 2026", 800)
            records.append(SourceRecord(
                external_id=f"bando-annuale-2026-{key.replace(' ', '-')}",
                title=f"Bando annuale 2026 — {label}", official_url=self.page_url,
                funder=self.funder, programme=self.programme,
                eligible_entities=("Enti e organizzazioni ammissibili secondo il bando di settore",),
                description=compact(f"{self.source_label}: {context}. La presentazione avviene tramite ROL; verificare il bando di settore e il termine pubblicato.") ,
                source_status="UNKNOWN", territory="Sardegna",
            ))
        return records
