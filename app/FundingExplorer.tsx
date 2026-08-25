"use client";

import { useEffect, useMemo, useState } from "react";
import { DEMO_OPPORTUNITIES } from "./demo-data";
import {
  USER_FACING_THEMES,
  filterOpportunities,
  isNewOpportunity,
  userFacingThemes,
  type Opportunity,
} from "./funding-domain";

type SnapshotSource = {
  sourceId: string;
  label: string;
  kind: "live" | "fixture";
  status: "LIVE" | "FIXTURE_ONLY" | "ERROR" | "STALE";
  fetchedRecords: number;
  publishedRecords: number;
  currentRecords?: number;
  archiveRecords?: number;
  new?: number;
  updated?: number;
  unchanged?: number;
  warnings: string[];
};

type SnapshotEnvelope = {
  schemaVersion: number;
  dataset?: "current" | "archive";
  generatedAt: string;
  asOfDate: string;
  complete: boolean;
  recordCount: number;
  recordCountCurrent?: number;
  recordCountArchive?: number;
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
  return { OPEN: "Aperti", UPCOMING: "In arrivo", CLOSED: "Scaduti", UNKNOWN: "Da verificare" }[status];
}

function updatedLabel(data: SnapshotEnvelope | null) {
  if (!data) return "Caricamento dati…";
  const stamp = new Date(data.generatedAt);
  if (!Number.isFinite(stamp.getTime())) return "Dati aggiornati di recente";
  const today = new Date();
  const sameDay = stamp.toLocaleDateString("it-IT") === today.toLocaleDateString("it-IT");
  return sameDay ? "Aggiornato oggi" : `Ultimo aggiornamento: ${stamp.toLocaleDateString("it-IT")}`;
}

function sortResults(items: Opportunity[]) {
  const rank = { Alta: 0, Media: 1, Bassa: 2 } as const;
  return [...items].sort((a, b) => (rank[a.relevance] - rank[b.relevance])
    || (a.deadline ?? "9999-12-31").localeCompare(b.deadline ?? "9999-12-31")
    || (a.firstSeen ?? "9999-12-31").localeCompare(b.firstSeen ?? "9999-12-31")
    || a.title.localeCompare(b.title, "it"));
}

export function FundingExplorer() {
  const [query, setQuery] = useState("");
  const [themes, setThemes] = useState<string[]>([]);
  const [territory, setTerritory] = useState("all");
  const [status, setStatus] = useState("current");
  const [deadline, setDeadline] = useState("all");
  const [applicant, setApplicant] = useState("all");
  const [newOnly, setNewOnly] = useState(false);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [includeLowRelevance, setIncludeLowRelevance] = useState(false);
  const [showOtherFilters, setShowOtherFilters] = useState(false);
  const [active, setActive] = useState<Opportunity | null>(null);
  const [favorites, setFavorites] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("fip-favorites") ?? "[]"); } catch { return []; }
  });
  const [currentOpportunities, setCurrentOpportunities] = useState<Opportunity[]>(DEMO_OPPORTUNITIES);
  const [snapshot, setSnapshot] = useState<SnapshotEnvelope | null>(null);
  const [archive, setArchive] = useState<SnapshotEnvelope | null>(null);
  const [viewMode, setViewMode] = useState<"current" | "archive">("current");
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(60);

  useEffect(() => {
    let cancelled = false;
    fetch("/data/opportunities-current.json", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`Dati HTTP ${response.status}`)))
      .then((payload: unknown) => {
        if (cancelled) return;
        if (!isSnapshotEnvelope(payload) || payload.opportunities.some((item) => typeof item.id !== "string" || typeof item.title !== "string")) {
          throw new Error("Dati non validi");
        }
        setCurrentOpportunities(payload.opportunities);
        setSnapshot(payload);
      })
      .catch((error: unknown) => {
        if (!cancelled) setSnapshotError(error instanceof Error ? error.message : "Dati non disponibili");
      });
    return () => { cancelled = true; };
  }, []);

  async function loadExpired() {
    if (archive) {
      setViewMode("archive");
      setStatus("all");
      setIncludeLowRelevance(true);
      return;
    }
    try {
      const response = await fetch("/data/opportunities-archive.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Dati scaduti HTTP ${response.status}`);
      const payload: unknown = await response.json();
      if (!isSnapshotEnvelope(payload)) throw new Error("Dati scaduti non validi");
      setArchive(payload);
      setViewMode("archive");
      setStatus("all");
      setIncludeLowRelevance(true);
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : "Dati scaduti non disponibili");
    }
  }

  function returnToCurrent() {
    setViewMode("current");
    setStatus("current");
    setIncludeLowRelevance(false);
  }

  const opportunities = useMemo(() => viewMode === "archive" ? (archive?.opportunities ?? []) : currentOpportunities, [viewMode, archive, currentOpportunities]);
  const results = useMemo(() => sortResults(filterOpportunities(opportunities, {
    query, themes, territory, status, deadline, applicant,
    favoriteIds: favorites, favoritesOnly, newOnly, includeLowRelevance,
  })), [opportunities, query, themes, territory, status, deadline, applicant, favorites, favoritesOnly, newOnly, includeLowRelevance]);
  const visibleResults = results.slice(0, visibleCount);
  const activeCount = [query.trim(), themes.length, territory !== "all", status !== "current", deadline !== "all", applicant !== "all", newOnly, favoritesOnly, includeLowRelevance].filter(Boolean).length;

  function toggleTheme(theme: string) {
    setThemes((current) => current.includes(theme) ? current.filter((item) => item !== theme) : [...current, theme]);
  }
  function toggleFavorite(id: string) {
    setFavorites((current) => {
      const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
      localStorage.setItem("fip-favorites", JSON.stringify(next));
      return next;
    });
  }
  function reset() {
    setQuery("");
    setThemes([]);
    setTerritory("all");
    setStatus(viewMode === "archive" ? "all" : "current");
    setDeadline("all");
    setApplicant("all");
    setNewOnly(false);
    setFavoritesOnly(false);
    setIncludeLowRelevance(viewMode === "archive");
  }
  function activateNew() {
    setNewOnly(true);
    setFavoritesOnly(false);
    setStatus("current");
    setIncludeLowRelevance(false);
    document.getElementById("bandi")?.scrollIntoView({ behavior: "smooth" });
  }
  function activateUpcoming() {
    setNewOnly(false);
    setFavoritesOnly(false);
    setStatus("UPCOMING");
    setIncludeLowRelevance(false);
    document.getElementById("bandi")?.scrollIntoView({ behavior: "smooth" });
  }
  function activateDeadline() {
    setNewOnly(false);
    setStatus("OPEN");
    setDeadline("30");
    setIncludeLowRelevance(false);
    document.getElementById("bandi")?.scrollIntoView({ behavior: "smooth" });
  }
  function selectStatus(value: string) {
    if (value === "CLOSED") {
      void loadExpired();
      return;
    }
    setStatus(value);
    setIncludeLowRelevance(false);
  }

  const warning = snapshotError || (snapshot && !snapshot.complete
    ? "Alcune fonti non sono state aggiornate oggi. I dati precedentemente verificati restano disponibili."
    : null);

  return <main>
    <header className="topbar"><a href="#top" className="brand"><span>FIP</span><strong>Funding Intelligence<br />for Psychology</strong></a><nav><a href="#bandi">Bandi</a><button onClick={activateNew}>Nuovi</button><button onClick={activateUpcoming}>In arrivo</button><button onClick={() => { setFavoritesOnly((value) => !value); setStatus("current"); }}>{favoritesOnly ? "Tutti" : "Preferiti"} <small>{favorites.length}</small></button><a href="#info">Informazioni</a></nav></header>

    <section className="hero" id="top">
      <p className="eyebrow">Finanziamenti, spiegati con parole semplici</p>
      <h1>Trova finanziamenti per progetti psicologici</h1>
      <p className="lead">Descrivi la tua idea: puoi cercare per tema, territorio e scadenza senza conoscere programmi o codici amministrativi.</p>
      <label className="hero-search"><span>Che progetto hai in mente?</span><div><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Es. salute mentale degli adolescenti, caregiver, inclusione scolastica..." /><a href="#bandi">Cerca</a></div></label>
      <div className="quick-links"><button onClick={activateNew}>Nuovi</button><button onClick={activateDeadline}>In scadenza</button><button onClick={activateUpcoming}>In arrivo</button></div>
    </section>

    <section className="macro-browser" aria-labelledby="theme-title"><div className="section-title"><div><p className="eyebrow">Parti dal tuo ambito</p><h2 id="theme-title">Scegli un’area di interesse</h2></div><p>Puoi scegliere più aree: verranno incluse le opportunità che corrispondono ad almeno una selezione.</p></div><div className="macro-grid">{USER_FACING_THEMES.map((theme) => <button className={themes.includes(theme) ? "selected" : ""} key={theme} onClick={() => toggleTheme(theme)}>{theme}{themes.includes(theme) && <span aria-hidden="true">✓</span>}</button>)}</div></section>

    <section className="results" id="bandi"><div className="results-heading"><div><p className="eyebrow">{viewMode === "archive" ? "Scaduti" : "Opportunità"}</p><h2>{results.length} {results.length === 1 ? "risultato" : "risultati"}</h2>{viewMode === "archive" && <p className="expired-note">Questi bandi non sono più aperti, ma possono essere utili per individuare programmi ricorrenti e opportunità future.</p>}</div><div><button className="filter-toggle" onClick={() => setShowOtherFilters((value) => !value)}>Filtri {activeCount > 0 && <span>{activeCount}</span>}</button>{viewMode === "archive" ? <button className="filter-toggle" onClick={returnToCurrent}>Torna agli aperti</button> : <button className="filter-toggle" onClick={loadExpired}>Consulta anche i bandi scaduti</button>}</div></div>
      <div className={`update-row ${warning ? "warning" : ""}`} role={warning ? "status" : undefined}>{warning ?? updatedLabel(snapshot)}</div>
      <div className={`filter-panel ${showOtherFilters ? "open" : ""}`}>
        <div className="theme-filter"><span>Tema</span><div>{USER_FACING_THEMES.map((theme) => <button className={themes.includes(theme) ? "selected" : ""} key={theme} onClick={() => toggleTheme(theme)}>{theme}</button>)}</div></div>
        <label><span>Territorio</span><select value={territory} onChange={(event) => setTerritory(event.target.value)}><option value="all">Tutti</option><option value="Veneto">Veneto</option><option value="Italia">Italia / nazionale</option><option value="Europa">Europa</option><option value="Altre regioni">Altre regioni</option></select></label>
        <label><span>Scadenza</span><select value={deadline} onChange={(event) => setDeadline(event.target.value)}><option value="all">Qualsiasi</option><option value="30">Entro 30 giorni</option><option value="90">Entro 90 giorni</option></select></label>
        <label><span>Chi può partecipare</span><select value={applicant} onChange={(event) => setApplicant(event.target.value)}><option value="all">Tutti / da verificare</option><option value="public">Enti pubblici</option><option value="ets">ETS / non profit</option><option value="research">Università / ricerca</option><option value="business">Imprese</option><option value="professional">Professionisti</option><option value="education">Scuole / formazione</option><option value="other">Altro</option><option value="unknown">Non indicato</option></select></label>
        {showOtherFilters && <div className="other-filters"><label><span>Stato</span><select value={status} onChange={(event) => selectStatus(event.target.value)}><option value="current">Aperti e in arrivo</option><option value="OPEN">Solo aperti</option><option value="UPCOMING">Solo in arrivo</option><option value="all">Tutti gli stati</option><option value="CLOSED">Scaduti</option><option value="UNKNOWN">Da verificare</option></select></label><label className="checkbox"><input type="checkbox" checked={includeLowRelevance} onChange={(event) => setIncludeLowRelevance(event.target.checked)} /><span>Mostra anche opportunità meno pertinenti</span></label><button className="expired-link" onClick={loadExpired}>Consulta anche i bandi scaduti</button></div>}
        {activeCount > 0 && <button className="reset" onClick={reset}>Azzera filtri</button>}
      </div>
      {activeCount > 0 && <div className="active-chips">{query.trim() && <button onClick={() => setQuery("")}>“{query}” ×</button>}{newOnly && <button onClick={() => setNewOnly(false)}>Nuovi ×</button>}{favoritesOnly && <button onClick={() => setFavoritesOnly(false)}>Preferiti ×</button>}{themes.map((theme) => <button key={theme} onClick={() => toggleTheme(theme)}>{theme} ×</button>)}{territory !== "all" && <button onClick={() => setTerritory("all")}>{territory} ×</button>}{status !== "current" && <button onClick={() => setStatus("current")}>{status === "all" ? "Tutti gli stati" : statusLabel(status as Opportunity["status"])} ×</button>}{deadline !== "all" && <button onClick={() => setDeadline("all")}>Entro {deadline} giorni ×</button>}{applicant !== "all" && <button onClick={() => setApplicant("all")}>{applicant} ×</button>}{includeLowRelevance && <button onClick={() => setIncludeLowRelevance(false)}>Meno pertinenti ×</button>}</div>}
      <div className="cards">{visibleResults.map((item) => { const itemThemes = userFacingThemes(item); return <article className={`card ${item.status === "UPCOMING" ? "upcoming" : ""}`} key={item.id}><div className="card-head"><span className={`status ${item.status.toLowerCase()}`}>{statusLabel(item.status)}</span><div>{isNewOpportunity(item) && <span className="new-badge">Nuovo</span>}<button className="favorite" onClick={() => toggleFavorite(item.id)} aria-label={favorites.includes(item.id) ? "Rimuovi dai preferiti" : "Salva nei preferiti"}>{favorites.includes(item.id) ? "★" : "☆"}</button></div></div><h3>{item.title}</h3><p className="funder">{item.funder} · {item.territory}</p><div className="facts"><span><small>{item.status === "UPCOMING" ? "Apertura prevista" : item.status === "OPEN" ? "Scadenza" : "Stato"}</small>{item.status === "UPCOMING" ? item.openingDate ?? "Da definire" : item.status === "OPEN" ? item.deadline ?? "Da verificare" : statusLabel(item.status)}</span><span><small>Quanto</small>{item.amount ?? "Non indicato"}</span></div><div className="tags">{itemThemes.slice(0, 2).map((theme) => <span key={theme}>{theme}</span>)}{itemThemes.length > 2 && <span>+{itemThemes.length - 2}</span>}</div><div className="card-footer"><span>Rilevanza psicologica: <strong>{item.relevance}</strong></span><button onClick={() => setActive(item)}>Dettagli</button></div>{item.status === "UPCOMING" && <p className="caution">Le condizioni definitive potranno cambiare.</p>}</article>; })}</div>
      {visibleResults.length < results.length && <div className="results-more"><p>Mostrate {visibleResults.length} schede per mantenere la consultazione rapida.</p><button className="filter-toggle" onClick={() => setVisibleCount((count) => count + 60)}>Mostra altre</button></div>}
      {results.length === 0 && <div className="empty"><strong>Non abbiamo trovato opportunità con questi criteri.</strong><p>Prova ad ampliare il territorio, rimuovere un filtro o includere anche i bandi in arrivo.</p><button onClick={reset}>Azzera filtri</button></div>}
    </section>

    <section className="info" id="info"><p className="eyebrow">Trasparenza</p><h2>La fonte ufficiale viene prima di tutto.</h2>{snapshot ? <p>La consultazione usa dati raccolti il {new Date(snapshot.generatedAt).toLocaleString("it-IT")} da {snapshot.liveSourceCount} fonti ufficiali. La rilevanza psicologica è una classificazione testuale, non un giudizio di ammissibilità: per requisiti, scadenze e importi vale sempre il testo ufficiale.</p> : <p>La consultazione separa la rilevanza psicologica dalla possibilità di partecipare. Per requisiti, scadenze e importi vale sempre il testo ufficiale della fonte.</p>}</section>
    <footer><strong>Funding Intelligence for Psychology</strong><span>Fonti ufficiali · {updatedLabel(snapshot)}</span></footer>

    {active && <div className="modal-backdrop" onMouseDown={() => setActive(null)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onMouseDown={(event) => event.stopPropagation()}><button className="close" onClick={() => setActive(null)} aria-label="Chiudi">×</button><span className={`status ${active.status.toLowerCase()}`}>{statusLabel(active.status)}</span><h2 id="detail-title">{active.title}</h2><div className="brief"><div><small>Cosa finanzia</small><p>{active.summary}</p></div><div><small>Chi può partecipare</small><p>{active.eligibleEntities.length ? active.eligibleEntities.join(", ") : "Non indicato nella fonte acquisita"}</p></div><div><small>Quanto</small><p>{active.amount ?? "Non indicato nella fonte acquisita"}</p></div><div><small>Dove</small><p>{active.territory}{active.regions?.length ? ` · ${active.regions.join(", ")}` : ""}</p></div><div><small>{active.status === "UPCOMING" ? "Apertura prevista" : active.status === "OPEN" ? "Scadenza" : "Stato"}</small><p>{active.status === "UPCOMING" ? active.openingDate ?? "Da definire" : active.status === "OPEN" ? active.deadline ?? "Da verificare" : statusLabel(active.status)}</p></div></div><h3>Perché può essere interessante</h3><p><strong>Rilevanza {active.relevance.toLowerCase()}.</strong> {active.relevanceWhy}</p><h3>Aree di interesse</h3><div className="tags">{userFacingThemes(active).length ? userFacingThemes(active).map((theme) => <span key={theme}>{theme}</span>) : <span>Nessuna area rilevata automaticamente</span>}</div><div className="eligibility"><strong>Possibilità di partecipare: da verificare</strong><p>Consulta sempre i requisiti nel testo ufficiale. La classificazione non interpreta l’ammissibilità.</p></div><div className="source"><span>{active.demo ? "Scheda locale" : `Fonte dati: ${active.sourceLabel ?? active.sourceId ?? "ufficiale"}`} · ultimo controllo: {active.lastVerified}</span><span>{active.aggregatorUrl && active.aggregatorUrl !== active.officialUrl ? <a href={active.aggregatorUrl} target="_blank" rel="noreferrer">Fonte dati aggregata ↗</a> : null} <a href={active.officialUrl} target="_blank" rel="noreferrer">Apri la pagina ufficiale ↗</a></span></div></section></div>}
  </main>;
}
