declare module "sql.js" {
  type SqlValue = number | string | Uint8Array | null;
  type QueryResult = { columns: string[]; values: SqlValue[][] };

  class Database {
    constructor(data?: Uint8Array);
    exec(sql: string): QueryResult[];
    close(): void;
  }

  export default function initSqlJs(config?: {
    locateFile?: (file: string) => string;
  }): Promise<{ Database: typeof Database }>;
}
