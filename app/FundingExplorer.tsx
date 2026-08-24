"use client";

import { useEffect, useMemo, useState } from "react";
import { DEMO_OPPORTUNITIES, MACRO_AREAS } from "./demo-data";
import { filterOpportunities, type Opportunity } from "./funding-domain";

const HOME_MACROS = ["Salute mentale e benessere", "Minori e adolescenti", "Scuola, università e formazione", "Famiglia e genitorialità", "Inclusione sociale e vulnerabilità", "Disabilità e neurodiversità", "Anziani, ageing e caregiver", "Violenza, trauma e tutela", "Dipendenze", "Lavoro, organizzazioni e occupazione", "Comunità, welfare e sviluppo territoriale", "Digitale, innovazione e AI"];

type SnapshotSource = {
  sourceId: string;
  label: string;
  kind: "live" | "fixture";
  status: "LIVE" | "FIXTURE_ONLY" | "ERROR";
  fetchedRecords: number;
  publishedRecords: number;
  warnings: string[];
};

type SnapshotEnvelope = {
  schemaVersion: number;
  generatedAt: string;
  asOfDate: string;
  complete: boolean;
  recordCount: number;
  liveSourceCount: number;
  sourceCount: number;
  sources: SnapshotSource[];
  warnings: string[];
  notImplemented: string[];
  opportunities: Opportunity[];
};

function isSnapshotEnvelope(value: unknown): value is SnapshotEnvelope {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<SnapshotEnvelope>;
  return Array.isArray(candidate.opportunities)
    && typeof candidate.recordCount === "number"
    && Array.isArray(candidate.sources);
}

function statusLabel(status: Opportunity["status"]) {
  return { OPEN: "Aperto", UPCOMING: "In arrivo", CLOSED: "Chiuso", UNKNOWN: "Da verificare" }[status];
}

function shortMacro(value: string) {
  return value.replace(" e benessere", "").replace(", università e formazione", "").replace(" e vulnerabilità", "").replace(" e neurodiversità", "").replace(", ageing e caregiver", " e caregiver").replace(", welfare e sviluppo territoriale", "").replace(", innovazione e AI", " e AI");
}

export function FundingExplorer() {
  const [query, setQuery] = useState("");
  const [macros, setMacros] = useState<string[]>([]);
  const [territory, setTerritory] = useState("all");
  const [status, setStatus] = useState("all");
  const [deadline, setDeadline] = useState("all");
  const [showAll, setShowAll] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [active, setActive] = useState<Opportunity | null>(null);
  const [favorites, setFavorites] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("fip-favorites") ?? "[]"); } catch { return []; }
  });
  const [opportunities, setOpportunities] = useState<Opportunity[]>(DEMO_OPPORTUNITIES);
  const [snapshot, setSnapshot] = useState<SnapshotEnvelope | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(60);

  useEffect(() => {
    let cancelled = false;
    fetch("/data/opportunities.json", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`snapshot HTTP ${response.status}`)))
      .then((payload: unknown) => {
        if (cancelled) return;
        if (!isSnapshotEnvelope(payload) || payload.opportunities.some((item) => typeof item.id !== "string" || typeof item.title !== "string")) {
          throw new Error("snapshot non valido");
        }
        setOpportunities(payload.opportunities);
        setSnapshot(payload);
      })
      .catch((error: unknown) => {
        if (!cancelled) setSnapshotError(error instanceof Error ? error.message : "snapshot non disponibile");
      });
    return () => { cancelled = true; };
  }, []);

  const results = useMemo(() => filterOpportunities(opportunities, { query, macroAreas: macros, territory, status, deadline }), [opportunities, query, macros, territory, status, deadline]);
  const visibleResults = results.slice(0, visibleCount);
  const activeCount = [query.trim(), macros.length, territory !== "all", status !== "all", deadline !== "all"].filter(Boolean).length;

  function toggleMacro(area: string) { setMacros((current) => current.includes(area) ? current.filter((item) => item !== area) : [...current, area]); }
  function toggleFavorite(id: string) {
    setFavorites((current) => { const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id]; localStorage.setItem("fip-favorites", JSON.stringify(next)); return next; });
  }
  function reset() { setQuery(""); setMacros([]); setTerritory("all"); setStatus("all"); setDeadline("all"); }

  return <main>
    <header className="topbar"><a href="#top" className="brand"><span>FIP</span><strong>Funding Intelligence<br/>for Psychology</strong></a><nav><a href="#bandi">Bandi</a><button onClick={() => setStatus("UPCOMING")}>In arrivo</button><button onClick={() => { setStatus("all"); setQuery(""); setMacros([]); }}>Preferiti <small>{favorites.length}</small></button><a href="#info">Informazioni</a></nav></header>

    <section className="prototype" role="status">{snapshot ? <><strong>Snapshot iniziale attivo.</strong> {snapshot.recordCount.toLocaleString("it-IT")} opportunità da {snapshot.liveSourceCount} fonti ufficiali sono consultabili. {snapshot.complete ? "Date e importi mancanti restano esplicitamente non indicati." : "Alcune fonti non erano disponibili durante l'ultimo popolamento."}</> : <><strong>Prototipo UX verificabile.</strong> Le schede sono scenari dimostrativi, non bandi reali. L’adapter UE è stato verificato live; anche gli adapter nazionali, regionali e delle fondazioni sono stati verificati sul contratto della fonte, ma i dati non sono ancora sincronizzati nello snapshot pubblico.</>}{snapshotError && <span> Caricamento dati reali non riuscito: viene mantenuto il fallback dimostrativo.</span>}</section>

    <section className="hero" id="top">
      <p className="eyebrow">Finanziamenti, spiegati con parole semplici</p>
      <h1>Trova finanziamenti per progetti psicologici</h1>
      <p className="lead">Descrivi la tua idea: puoi cercare per tema, territorio e scadenza senza conoscere programmi o codici amministrativi.</p>
      <label className="hero-search"><span>Che progetto hai in mente?</span><div><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Es. salute mentale degli adolescenti, caregiver, inclusione scolastica, burnout..."/><a href="#bandi">Cerca</a></div></label>
      <div className="quick-links"><button onClick={() => setStatus("all")}>Nuovi</button><button onClick={() => { setStatus("OPEN"); setDeadline("30"); }}>In scadenza</button><button onClick={() => setStatus("UPCOMING")}>In arrivo</button><button onClick={reset}>Tutti i bandi</button></div>
    </section>

    <section className="macro-browser" aria-labelledby="macro-title"><div className="section-title"><div><p className="eyebrow">Parti dal tuo ambito</p><h2 id="macro-title">Quale tema ti interessa?</h2></div><p>Puoi scegliere più aree. Le opportunità che corrispondono ad almeno una selezione saranno incluse.</p></div><div className="macro-grid">{(showAll ? MACRO_AREAS : HOME_MACROS).map((area) => <button className={macros.includes(area) ? "selected" : ""} key={area} onClick={() => toggleMacro(area)}>{shortMacro(area)}{macros.includes(area) && <span aria-hidden="true">✓</span>}</button>)}</div><button className="show-all" onClick={() => setShowAll((value) => !value)}>{showAll ? "Mostra meno" : "Mostra tutte le macroaree"}</button></section>

    <section className="results" id="bandi"><div className="results-heading"><div><p className="eyebrow">Opportunità</p><h2>{results.length} {results.length === 1 ? "risultato" : "risultati"}</h2></div><button className="filter-toggle" onClick={() => setShowFilters((value) => !value)}>Filtri {activeCount > 0 && <span>{activeCount}</span>}</button></div>
      <div className={`filter-panel ${showFilters ? "open" : ""}`}>
        <label><span>Territorio</span><select value={territory} onChange={(event) => setTerritory(event.target.value)}><option value="all">Tutti</option><option>Veneto</option><option>Italia</option><option>Unione Europea</option></select></label>
        <label><span>Stato</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Tutti gli stati</option><option value="OPEN">Aperti</option><option value="UPCOMING">In arrivo</option><option value="CLOSED">Chiusi</option><option value="UNKNOWN">Da verificare</option></select></label>
        <label><span>Scadenza</span><select value={deadline} onChange={(event) => setDeadline(event.target.value)}><option value="all">Qualsiasi</option><option value="30">Entro 30 giorni</option><option value="90">Entro 90 giorni</option></select></label>
        {activeCount > 0 && <button className="reset" onClick={reset}>Azzera filtri</button>}
      </div>
      {activeCount > 0 && <div className="active-chips">{macros.map((area) => <button key={area} onClick={() => toggleMacro(area)}>{shortMacro(area)} ×</button>)}{territory !== "all" && <button onClick={() => setTerritory("all")}>{territory} ×</button>}{status !== "all" && <button onClick={() => setStatus("all")}>{statusLabel(status as Opportunity["status"])} ×</button>}{deadline !== "all" && <button onClick={() => setDeadline("all")}>Entro {deadline} giorni ×</button>}</div>}
      <div className="cards">{visibleResults.map((item) => <article className={`card ${item.status === "UPCOMING" ? "upcoming" : ""}`} key={item.id}><div className="card-head"><span className={`status ${item.status.toLowerCase()}`}>{statusLabel(item.status)}</span><button className="favorite" onClick={() => toggleFavorite(item.id)} aria-label={favorites.includes(item.id) ? "Rimuovi dai preferiti" : "Salva nei preferiti"}>{favorites.includes(item.id) ? "★" : "☆"}</button></div><h3>{item.title}</h3><p className="funder">{item.funder} · {item.territory}</p><div className="facts"><span><small>{item.status === "UPCOMING" ? "Apertura prevista" : item.status === "OPEN" ? "Scadenza" : "Stato"}</small>{item.status === "UPCOMING" ? item.openingDate ?? "Da definire" : item.status === "OPEN" ? item.deadline ?? "Da verificare" : statusLabel(item.status)}</span><span><small>Quanto</small>{item.amount ?? "Non indicato"}</span></div><div className="tags">{item.macroAreas.slice(0,3).map((area) => <span key={area}>{shortMacro(area)}</span>)}</div><div className="card-footer"><span>Rilevanza psicologica: <strong>{item.relevance}</strong></span><button onClick={() => setActive(item)}>Dettagli</button></div>{item.status === "UPCOMING" && <p className="caution">Le condizioni definitive potranno cambiare.</p>}</article>)}</div>
      {visibleResults.length < results.length && <div className="results-more"><p>Mostrate {visibleResults.length} schede per mantenere la consultazione rapida.</p><button className="filter-toggle" onClick={() => setVisibleCount((count) => count + 60)}>Mostra altre</button></div>}
      {results.length === 0 && <div className="empty"><strong>Non abbiamo trovato opportunità con questi criteri.</strong><p>Prova ad ampliare il territorio, rimuovere un filtro o includere anche i bandi in arrivo.</p><button onClick={reset}>Azzera filtri</button></div>}
    </section>

    <section className="info" id="info"><p className="eyebrow">Trasparenza</p><h2>La fonte ufficiale viene prima di tutto.</h2>{snapshot ? <p>La consultazione usa uno snapshot locale generato il {new Date(snapshot.generatedAt).toLocaleString("it-IT")} da {snapshot.liveSourceCount} adapter live. La rilevanza psicologica è una classificazione testuale, non un giudizio di ammissibilità: per requisiti, scadenze e importi vale sempre il testo ufficiale.</p> : <p>Questo prototipo separa rilevanza psicologica e possibilità di partecipare. Gli adapter UE, nazionali, Regione Veneto e fondazioni sono verificabili dal core locale, mentre le schede mostrate qui restano scenari dimostrativi in attesa della persistenza e della sincronizzazione notturna.</p>}</section>
    <footer><strong>Funding Intelligence for Psychology</strong><span>{snapshot ? "Snapshot locale · fonti ufficiali" : "Prototipo locale · nessuna API AI richiesta"}</span></footer>

    {active && <div className="modal-backdrop" onMouseDown={() => setActive(null)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onMouseDown={(event) => event.stopPropagation()}><button className="close" onClick={() => setActive(null)} aria-label="Chiudi">×</button><span className={`status ${active.status.toLowerCase()}`}>{statusLabel(active.status)}</span><h2 id="detail-title">{active.title}</h2><div className="brief"><div><small>Cosa finanzia</small><p>{active.summary}</p></div><div><small>Chi può partecipare</small><p>{active.eligibleEntities.length ? active.eligibleEntities.join(", ") : "Non indicato nella lista ufficiale"}</p></div><div><small>Quanto</small><p>{active.amount ?? "Non indicato"}</p></div><div><small>Dove</small><p>{active.territory}</p></div><div><small>{active.status === "UPCOMING" ? "Apertura prevista" : active.status === "OPEN" ? "Scadenza" : "Stato"}</small><p>{active.status === "UPCOMING" ? active.openingDate ?? "Da definire" : active.status === "OPEN" ? active.deadline ?? "Da verificare" : statusLabel(active.status)}</p></div></div><h3>Perché può essere interessante</h3><p><strong>Rilevanza {active.relevance.toLowerCase()}.</strong> {active.relevanceWhy}</p><h3>Macroaree</h3><div className="tags">{active.macroAreas.length ? active.macroAreas.map((area) => <span key={area}>{area}</span>) : <span>Nessuna macroarea rilevata automaticamente</span>}</div><div className="eligibility"><strong>Possibilità di partecipare: da verificare</strong><p>Consulta sempre i requisiti nel testo ufficiale. La classificazione non interpreta l’ammissibilità.</p></div><div className="source"><span>{active.demo ? "Scenario dimostrativo" : `Fonte ${active.sourceId ?? "ufficiale"}`} · ultimo controllo: {active.lastVerified}</span><a href={active.officialUrl} target="_blank" rel="noreferrer">Apri la pagina ufficiale ↗</a></div></section></div>}
  </main>;
}
