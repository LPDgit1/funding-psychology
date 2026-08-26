from __future__ import annotations

import re

from funding_core.adapters import AdapterError
from funding_core.models import SourceRecord

from ._common import compact, decode_html


class IntesaBeneficenzaAdapter:
    source_id = "intesa_beneficenza"
    page_url = "https://group.intesasanpaolo.com/it/sociale/fondo-di-beneficenza/come-richiedere-un-contributo"
    source_label = "Fondo di Beneficenza Intesa Sanpaolo"
    funder = "Intesa Sanpaolo — Fondo di Beneficenza"
    programme = "Fondo di Beneficenza 2025-2026"

    def fetch(self, policy=None) -> bytes:
        # Reuse the proven bounded HTML transport without introducing a new
        # dependency; this page is the canonical application instructions page.
        from funding_core.adapters import FetchPolicy, _HtmlOpportunityListAdapter
        shell = _HtmlOpportunityListAdapter()
        shell.page_url = self.page_url
        shell.source_label = self.source_label
        return shell.fetch(policy or FetchPolicy(max_bytes=8_000_000))

    def parse(self, raw: bytes | str) -> list[SourceRecord]:
        text = decode_html(raw)
        if not re.search(r"candida il tuo progetto|come richiedere un contributo|chi può presentare", text, re.I):
            raise AdapterError("Intesa Beneficenza application page has no standing-opportunity markers")
        eligibility = "Enti senza finalità di lucro con sede in Italia, registrati in un registro pubblico"
        description = compact(
            "Richiesta rolling di liberalità territoriali (fino a €5.000) o centrali (oltre €5.000). "
            "Le proposte sono valutate durante l'anno fino a esaurimento del plafond; per la ricerca medica "
            "la pagina indica il mese di maggio come termine annuale. Linee guida e regolamento sono richiamati nella pagina ufficiale. "
            + text,
            1600,
        )
        return [SourceRecord(
            external_id="fondo-beneficenza-current",
            title="Fondo di Beneficenza Intesa Sanpaolo — richiesta di contributo",
            official_url=self.page_url,
            funder=self.funder,
            programme=self.programme,
            deadline=None,
            eligible_entities=(eligibility,),
            description=description,
            source_status="OPEN",
            status_authoritative=True,
            territory="Italia",
        )]

