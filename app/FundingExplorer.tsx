"use client";

import { useEffect, useMemo, useState } from "react";
import { DEMO_OPPORTUNITIES, MACRO_AREAS } from "./demo-data";
import { filterOpportunities, type Opportunity } from "./funding-domain";

const HOME_MACROS = ["Salute mentale e benessere", "Minori e adolescenti", "Scuola, università e formazione", "Famiglia e genitorialità", "Inclusione sociale e vulnerabilità", "Disabilità e neurodiversità", "Anziani, ageing e caregiver", "Violenza, trauma e tutela", "Dipendenze", "Lavoro, organizzazioni e occupazione", "Comunità, welfare e sviluppo territoriale", "Digitale, innovazione e AI"];

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
  const [favorites, setFavorites] = useState<string[]>([]);

  useEffect(() => {
    try { setFavorites(JSON.parse(localStorage.getItem("fip-favorites") ?? "[]")); } catch { setFavorites([]); }
  }, []);

  const results = useMemo(() => filterOpportunities(DEMO_OPPORTUNITIES, { query, macroAreas: macros, territory, status, deadline }), [query, macros, territory, status, deadline]);
  const activeCount = [query.trim(), macros.length, territory !== "all", status !== "all", deadline !== "all"].filter(Boolean).length;

  function toggleMacro(area: string) { setMacros((current) => current.includes(area) ? current.filter((item) => item !== area) : [...current, area]); }
  function toggleFavorite(id: string) {
    setFavorites((current) => { const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id]; localStorage.setItem("fip-favorites", JSON.stringify(next)); return next; });
  }
  function reset() { setQuery(""); setMacros([]); setTerritory("all"); setStatus("all"); setDeadline("all"); }

  return <main>
    <header className="topbar"><a href="#top" className="brand"><span>FIP</span><strong>Funding Intelligence<br/>for Psychology</strong></a><nav><a href="#bandi">Bandi</a><button onClick={() => setStatus("UPCOMING")}>In arrivo</button><button onClick={() => { setStatus("all"); setQuery(""); setMacros([]); }}>Preferiti <small>{favorites.length}</small></button><a href="#info">Informazioni</a></nav></header>

    <section className="prototype" role="status"><strong>Prototipo UX verificabile.</strong> Le schede sono scenari dimostrativi, non bandi reali. L’adapter UE è stato verificato live e l’export Incentivi.gov.it è stato verificato live, ma i dati non sono ancora sincronizzati nello snapshot pubblico.</section>

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
        <label><span>Stato</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Aperti e in arrivo</option><option value="OPEN">Aperti</option><option value="UPCOMING">In arrivo</option></select></label>
        <label><span>Scadenza</span><select value={deadline} onChange={(event) => setDeadline(event.target.value)}><option value="all">Qualsiasi</option><option value="30">Entro 30 giorni</option><option value="90">Entro 90 giorni</option></select></label>
        {activeCount > 0 && <button className="reset" onClick={reset}>Azzera filtri</button>}
      </div>
      {activeCount > 0 && <div className="active-chips">{macros.map((area) => <button key={area} onClick={() => toggleMacro(area)}>{shortMacro(area)} ×</button>)}{territory !== "all" && <button onClick={() => setTerritory("all")}>{territory} ×</button>}{status !== "all" && <button onClick={() => setStatus("all")}>{status === "OPEN" ? "Aperti" : "In arrivo"} ×</button>}{deadline !== "all" && <button onClick={() => setDeadline("all")}>Entro {deadline} giorni ×</button>}</div>}
      <div className="cards">{results.map((item) => <article className={`card ${item.status === "UPCOMING" ? "upcoming" : ""}`} key={item.id}><div className="card-head"><span className={`status ${item.status.toLowerCase()}`}>{item.status === "OPEN" ? "Aperto" : "In arrivo"}</span><button className="favorite" onClick={() => toggleFavorite(item.id)} aria-label={favorites.includes(item.id) ? "Rimuovi dai preferiti" : "Salva nei preferiti"}>{favorites.includes(item.id) ? "★" : "☆"}</button></div><h3>{item.title}</h3><p className="funder">{item.funder} · {item.territory}</p><div className="facts"><span><small>{item.status === "UPCOMING" ? "Apertura prevista" : "Scadenza"}</small>{item.status === "UPCOMING" ? item.openingDate ?? "Da definire" : item.deadline ?? "Da verificare"}</span><span><small>Quanto</small>{item.amount ?? "Non indicato"}</span></div><div className="tags">{item.macroAreas.slice(0,3).map((area) => <span key={area}>{shortMacro(area)}</span>)}</div><div className="card-footer"><span>Rilevanza psicologica: <strong>{item.relevance}</strong></span><button onClick={() => setActive(item)}>Dettagli</button></div>{item.status === "UPCOMING" && <p className="caution">Le condizioni definitive potranno cambiare.</p>}</article>)}</div>
      {results.length === 0 && <div className="empty"><strong>Non abbiamo trovato opportunità con questi criteri.</strong><p>Prova ad ampliare il territorio, rimuovere un filtro o includere anche i bandi in arrivo.</p><button onClick={reset}>Azzera filtri</button></div>}
    </section>

    <section className="info" id="info"><p className="eyebrow">Trasparenza</p><h2>La fonte ufficiale viene prima di tutto.</h2><p>Questo prototipo separa rilevanza psicologica e possibilità di partecipare. Gli adapter Funding &amp; Tenders Portal UE e Incentivi.gov.it rispondono live, mentre le schede mostrate qui restano scenari dimostrativi in attesa della persistenza e della sincronizzazione notturna.</p></section>
    <footer><strong>Funding Intelligence for Psychology</strong><span>Prototipo locale · nessuna API AI richiesta</span></footer>

    {active && <div className="modal-backdrop" onMouseDown={() => setActive(null)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onMouseDown={(event) => event.stopPropagation()}><button className="close" onClick={() => setActive(null)} aria-label="Chiudi">×</button><span className={`status ${active.status.toLowerCase()}`}>{active.status === "OPEN" ? "Aperto" : "In arrivo"}</span><h2 id="detail-title">{active.title}</h2><div className="brief"><div><small>Cosa finanzia</small><p>{active.summary}</p></div><div><small>Chi può partecipare</small><p>{active.eligibleEntities.join(", ")}</p></div><div><small>Quanto</small><p>{active.amount ?? "Non indicato"}</p></div><div><small>Dove</small><p>{active.territory}</p></div><div><small>{active.status === "UPCOMING" ? "Apertura prevista" : "Scadenza"}</small><p>{active.status === "UPCOMING" ? active.openingDate : active.deadline}</p></div></div><h3>Perché può essere interessante</h3><p><strong>Rilevanza {active.relevance.toLowerCase()}.</strong> {active.relevanceWhy}</p><h3>Macroaree</h3><div className="tags">{active.macroAreas.map((area) => <span key={area}>{area}</span>)}</div><div className="eligibility"><strong>Possibilità di partecipare: da verificare</strong><p>Consulta sempre i requisiti nel testo ufficiale. Questo prototipo non interpreta l'ammissibilità.</p></div><div className="source"><span>Scenario dimostrativo · ultimo controllo struttura: {active.lastVerified}</span><a href={active.officialUrl} target="_blank" rel="noreferrer">Apri la pagina ufficiale di riferimento ↗</a></div></section></div>}
  </main>;
}
