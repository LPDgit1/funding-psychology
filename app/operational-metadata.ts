export type SnapshotSourceMetadata = {
  kind?: "live" | "fixture";
  status?: "LIVE" | "FIXTURE_ONLY" | "ERROR" | "STALE";
};

export type SnapshotMetadata = {
  generatedAt?: string;
  sourceCount?: number;
  liveSourceCount?: number;
  sourceHealth?: {
    totalSourceCount?: number;
    liveConfiguredSourceCount?: number;
    successfulSourceCount?: number;
    staleSourceCount?: number;
    errorSourceCount?: number;
    fixtureOnlySourceCount?: number;
  };
  sources?: SnapshotSourceMetadata[];
};

const ROME_TIME_ZONE = "Europe/Rome";
const HOUR = 60 * 60 * 1000;

function validDate(value: string | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

function numberOrFallback(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function dateParts(date: Date) {
  const parts = new Intl.DateTimeFormat("it-IT", {
    timeZone: ROME_TIME_ZONE,
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(date);
  return Object.fromEntries(parts.map(({ type, value }) => [type, value]));
}

function sameRomeDay(left: Date, right: Date): boolean {
  const formatter = new Intl.DateTimeFormat("it-IT", {
    timeZone: ROME_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(left) === formatter.format(right);
}

/** Human-readable Europe/Rome timestamp used in the public UI. */
export function updatedLabel(data: SnapshotMetadata | null, now = new Date()): string {
  if (!data) return "Caricamento dati…";
  const stamp = validDate(data.generatedAt);
  if (!stamp) return "Dati aggiornati di recente";
  const parts = dateParts(stamp);
  const time = `${parts.hour ?? ""}:${parts.minute ?? ""}`;
  return sameRomeDay(stamp, now)
    ? `Aggiornato oggi alle ${time}`
    : `Aggiornato il ${parts.day} ${parts.month} alle ${time}`;
}

/** Return null while fresh, a discreet warning after 36h, and a stronger one after 72h. */
export function freshnessWarning(data: SnapshotMetadata | null, now = new Date()): string | null {
  const stamp = validDate(data?.generatedAt);
  if (!stamp) return null;
  const age = now.getTime() - stamp.getTime();
  if (age <= 36 * HOUR) return null;
  if (age <= 72 * HOUR) return "I dati non risultano aggiornati nelle ultime 24 ore.";
  const days = Math.max(1, Math.floor(age / (24 * HOUR)));
  return `Ultimo aggiornamento disponibile: ${days} ${days === 1 ? "giorno" : "giorni"} fa. Alcune opportunità potrebbero essere cambiate.`;
}

/** Compact user-facing count of live sources that were consulted. */
export function sourceSummary(data: SnapshotMetadata | null): string {
  if (!data) return "Verifica delle fonti in corso.";
  const rows = Array.isArray(data.sources) ? data.sources : [];
  const liveRows = rows.filter((row) => row.kind === "live");
  const health = data.sourceHealth ?? {};
  const consulted = numberOrFallback(
    health.liveConfiguredSourceCount,
    liveRows.length || numberOrFallback(data.liveSourceCount, 0),
  );
  return `${consulted} ${consulted === 1 ? "fonte consultata" : "fonti consultate"}`;
}
