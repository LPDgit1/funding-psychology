import type { Opportunity } from "./funding-domain";
import { BUNDLED_DATA_BASE_URL, REMOTE_DATA_BASE_URL, REMOTE_HEALTH_URL } from "./data-config";

export type SnapshotSource = {
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

export type SnapshotEnvelope = {
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
  sourceHealth?: {
    totalSourceCount?: number;
    liveConfiguredSourceCount?: number;
    successfulSourceCount?: number;
    staleSourceCount?: number;
    errorSourceCount?: number;
    fixtureOnlySourceCount?: number;
  };
  sources: SnapshotSource[];
  warnings: string[];
  notImplemented: string[];
  opportunities: Opportunity[];
};

export type DailySyncHealth = {
  startedAt?: string;
  completedAt?: string;
  snapshotGeneratedAt?: string;
  sourcesAttempted?: number;
  LIVE?: string[];
  STALE?: string[];
  ERROR?: string[];
  FIXTURE_ONLY?: string[];
  sourceCounts?: SnapshotEnvelope["sourceHealth"];
  currentRecords?: number;
  archiveRecords?: number;
  snapshotValid?: boolean;
  syncStatus?: string;
  deploymentStatus?: string;
};

export type DataOrigin = "remote" | "bundled";

export type LoadedSnapshot = {
  snapshot: SnapshotEnvelope;
  origin: DataOrigin;
  health: DailySyncHealth | null;
  remoteVersion?: string;
};

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/** Minimal browser-side guard: transport JSON, generatedAt and usable records. */
export function isSnapshotEnvelope(value: unknown): value is Partial<SnapshotEnvelope> & Pick<SnapshotEnvelope, "generatedAt" | "opportunities"> {
  if (!isObject(value) || !nonEmptyString(value.generatedAt) || !Array.isArray(value.opportunities) || value.opportunities.length === 0) return false;
  return value.opportunities.every((item) => isObject(item) && nonEmptyString(item.id) && nonEmptyString(item.title));
}

function normalizeSnapshot(value: unknown): SnapshotEnvelope | null {
  if (!isSnapshotEnvelope(value)) return null;
  const candidate = value as Partial<SnapshotEnvelope>;
  return {
    schemaVersion: typeof candidate.schemaVersion === "number" ? candidate.schemaVersion : 2,
    dataset: candidate.dataset,
    generatedAt: value.generatedAt,
    asOfDate: typeof candidate.asOfDate === "string" ? candidate.asOfDate : "",
    complete: typeof candidate.complete === "boolean" ? candidate.complete : true,
    recordCount: typeof candidate.recordCount === "number" ? candidate.recordCount : value.opportunities.length,
    recordCountCurrent: candidate.recordCountCurrent,
    recordCountArchive: candidate.recordCountArchive,
    liveSourceCount: typeof candidate.liveSourceCount === "number" ? candidate.liveSourceCount : 0,
    sourceCount: typeof candidate.sourceCount === "number" ? candidate.sourceCount : (candidate.sources?.length ?? 0),
    sourceHealth: candidate.sourceHealth,
    sources: Array.isArray(candidate.sources) ? candidate.sources as SnapshotSource[] : [],
    warnings: Array.isArray(candidate.warnings) ? candidate.warnings : [],
    notImplemented: Array.isArray(candidate.notImplemented) ? candidate.notImplemented : [],
    opportunities: value.opportunities as Opportunity[],
  };
}

function isDailySyncHealth(value: unknown): value is DailySyncHealth {
  return isObject(value) && (
    nonEmptyString(value.snapshotGeneratedAt)
    || Array.isArray(value.LIVE)
    || Array.isArray(value.STALE)
    || Array.isArray(value.ERROR)
    || Array.isArray(value.FIXTURE_ONLY)
  );
}

export function versionedUrl(url: string, version?: string): string {
  if (!version) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}version=${encodeURIComponent(version)}`;
}

async function fetchJson(fetcher: FetchLike, url: string): Promise<unknown> {
  const response = await fetcher(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function tryHealth(fetcher: FetchLike): Promise<DailySyncHealth | null> {
  try {
    const value = await fetchJson(fetcher, REMOTE_HEALTH_URL);
    return isDailySyncHealth(value) ? value : null;
  } catch {
    return null;
  }
}

async function trySnapshot(fetcher: FetchLike, url: string): Promise<SnapshotEnvelope | null> {
  try {
    return normalizeSnapshot(await fetchJson(fetcher, url));
  } catch {
    return null;
  }
}

/** Load health first, then remote current, with the bundled file as fallback. */
export async function loadCurrentSnapshot(fetcher: FetchLike = fetch): Promise<LoadedSnapshot> {
  const health = await tryHealth(fetcher);
  const healthVersion = health?.snapshotGeneratedAt;
  const remote = await trySnapshot(fetcher, versionedUrl(`${REMOTE_DATA_BASE_URL}/opportunities-current.json`, healthVersion));
  if (remote) return { snapshot: remote, origin: "remote", health, remoteVersion: remote.generatedAt || healthVersion };

  const bundled = await trySnapshot(fetcher, `${BUNDLED_DATA_BASE_URL}/opportunities-current.json`);
  if (!bundled) throw new Error("Dati correnti non disponibili");
  return { snapshot: bundled, origin: "bundled", health, remoteVersion: healthVersion };
}

/** Archive remains lazy and follows the same remote-first/fallback policy. */
export async function loadArchiveSnapshot(version: string | undefined, fetcher: FetchLike = fetch): Promise<LoadedSnapshot> {
  const remote = await trySnapshot(fetcher, versionedUrl(`${REMOTE_DATA_BASE_URL}/opportunities-archive.json`, version));
  if (remote) return { snapshot: remote, origin: "remote", health: null, remoteVersion: remote.generatedAt || version };

  const bundled = await trySnapshot(fetcher, `${BUNDLED_DATA_BASE_URL}/opportunities-archive.json`);
  if (!bundled) throw new Error("Dati scaduti non disponibili");
  return { snapshot: bundled, origin: "bundled", health: null, remoteVersion: version };
}
