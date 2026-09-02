/** Public, non-secret runtime data configuration.
 *
 * GitHub Raw is used as the stable data origin. The `github-ready` branch is
 * updated by the daily workflow; the Site code itself is deployed only when
 * the application changes.
 */
export const REMOTE_REPOSITORY_BASE_URL =
  "https://raw.githubusercontent.com/LPDgit1/funding-psychology/github-ready";

export const REMOTE_DATA_BASE_URL = `${REMOTE_REPOSITORY_BASE_URL}/public/data`;
export const REMOTE_HEALTH_URL = `${REMOTE_REPOSITORY_BASE_URL}/reports/daily-sync-latest.json`;

export const BUNDLED_DATA_BASE_URL = "/data";
