# Funding Intelligence for Psychology v0.2.2b — report finale

## RELEVANCE

High: **4**

Medium: **23**

Low: **1881**

High/Medium obvious NOT_RELEVANT: **0**

Review High/Medium: **17 Relevant, 11 Borderline, 0 Not relevant**. NOT_RELEVANT evidenti: **0/28 = 0.0%** (PASS; soglia <=15%). Weighted relevance secondaria: **80.4%** (indicatore informativo, non gate primario; Relevant=1, Borderline=0.5, Not relevant=0).

Borderline retained: **11**. Sono conservati quando esiste un interesse progettuale plausibile per psicologi, ETS, cooperative sociali o servizi socio-sanitari, anche senza una keyword psicologica esplicita.

## FUNDING & TENDERS

404 retry: **implemented** solo nell'adapter Funding & Tenders, con massimo 2 retry aggiuntivi e multipart ricostruita integralmente a ogni tentativo.

Live validation: **LIVE / OK** — evidenza registrata in `reports/funding-tenders-live-validation.txt` (1.421 elementi trovati e 1.421 parsed).

Full sync: **STALE** — preservati 1022 record precedenti; warning: eu-funding-tenders: HTTP 404 from EU Funding & Tenders API (retry later); preserved 1022 previous records.

## GRANT TYPE 2

meaning: **Calls for proposals**; **included** nella configurazione `('1', '2', '8')`, verificato via FACET.

## TESTS

Targeted: retry 404 con request multipart distinta, preservazione dopo tre 404, grant type 2 e calibrazione dei pattern social-inclusivi. Full suite: **38 test Python e 9 test JavaScript**, eseguita una volta.

## STOPPING RULE

**NOT PASSED** — il 404 di Funding & Tenders resta non risolto dopo i retry; il fallback è mantenuto e il core non viene dichiarato chiuso.
