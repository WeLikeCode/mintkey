/**
 * RestResource — AdminJS BaseResource backed by admin-api HTTP calls.
 *
 * Replaces @adminjs/sql direct-DB adapter. All data comes from
 * http://admin-api:8080 (ADMIN_API_URL). No database connection.
 *
 * Source: ADR-0013; ADR-0014.5.
 */

import { BaseResource, BaseProperty, BaseRecord } from "adminjs";
import type { Filter, ActionContext } from "adminjs";

export interface PropertyDef {
  path: string;
  type?: "string" | "number" | "boolean" | "datetime" | "uuid";
  isId?: boolean;
  availableValues?: Array<{ value: string; label: string }>;
}

interface RestResourceConfig {
  id: string;
  name: string;
  listPath: string;
  getPath?: string;
  idField?: string;
  listKey: string;
  properties: PropertyDef[];
  /**
   * Allowlist of filter key names (matching AdminJS property names) that should
   * be forwarded to admin-api as query-string parameters.  Any Filter key not in
   * this list is silently ignored — it may still be used by AdminJS client-side
   * but will not be sent to the API.  Value must be non-empty string; blank
   * values are dropped.
   */
  filterKeys?: string[];
}

/**
 * RestDatabase — required by AdminJS.registerAdapter().
 * A thin stub that declares this adapter handles RestResource instances.
 */
export class RestDatabase {
  static isAdapterFor(resource: unknown): boolean {
    return resource instanceof RestResource;
  }

  id(): string { return "RestDatabase"; }
  name(): string { return "mintkey-api"; }
  resources(): RestResource[] { return []; }
}

export class RestResource extends BaseResource {
  static isAdapterFor(resource: unknown): boolean {
    return resource instanceof RestResource;
  }

  readonly _cfg: RestResourceConfig;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private config: RestResourceConfig;
  private apiUrl: string;

  constructor(config: RestResourceConfig | RestResource) {
    super();
    // AdminJS calls new Resource(rawResource) where rawResource is already our
    // RestResource instance. Unwrap the inner config in that case.
    this.config = config instanceof RestResource ? config._cfg : config;
    this._cfg = this.config;
    this.apiUrl = process.env.ADMIN_API_URL ?? "http://admin-api:8080";
  }

  id(): string {
    return this.config.id;
  }

  get resource(): string {
    return this.config.id;
  }

  name(): string {
    return this.config.name;
  }

  databaseName(): string {
    return "mintkey-api";
  }

  properties(): BaseProperty[] {
    return this.config.properties.map((p) => {
      const prop = new BaseProperty({ path: p.path, type: p.type ?? "string", isId: p.isId ?? false });
      if (p.availableValues) {
        // Attach availableValues so AdminJS renders a select dropdown
        (prop as unknown as { availableValues: typeof p.availableValues }).availableValues = p.availableValues;
      }
      return prop;
    });
  }

  property(path: string): BaseProperty | null {
    const def = this.config.properties.find((p) => p.path === path);
    if (!def) return null;
    const prop = new BaseProperty({ path: def.path, type: def.type ?? "string", isId: def.isId ?? false });
    if (def.availableValues) {
      (prop as unknown as { availableValues: typeof def.availableValues }).availableValues = def.availableValues;
    }
    return prop;
  }

  private _sessionHeaders(context?: ActionContext): Record<string, string> {
    const admin = context?.currentAdmin as { sessionToken?: string; isPlatformAdmin?: boolean } | undefined;
    const tok = admin?.sessionToken;
    const headers: Record<string, string> = tok ? { Cookie: `mintkey_session=${tok}` } : {};
    if (admin?.isPlatformAdmin === true) {
      headers["X-Platform-Admin"] = "true";
    }
    return headers;
  }

  async find(
    filter: Filter,
    _options: { limit?: number; offset?: number; sort?: { sortBy?: string; direction?: "asc" | "desc" } },
    context?: ActionContext
  ): Promise<BaseRecord[]> {
    const tenantId = (context?.currentAdmin as { tenantId?: string } | undefined)?.tenantId;

    let path = this.config.listPath;
    if (path.includes("{tenantId}")) {
      if (!tenantId) return [];
      path = path.replace("{tenantId}", tenantId);
    }

    const qs = this._buildQueryString(filter);
    const url = `${this.apiUrl}${path}${qs ? `?${qs}` : ""}`;

    try {
      const resp = await fetch(url, { headers: this._sessionHeaders(context) });
      if (!resp.ok) return [];
      const data = await resp.json() as Record<string, unknown>;
      const items = data[this.config.listKey];
      if (!Array.isArray(items)) return [];
      return items.map((item) => new BaseRecord(item as Record<string, unknown>, this));
    } catch {
      return [];
    }
  }

  /**
   * Translate AdminJS filter keys → URL query string using the resource's
   * `filterKeys` allowlist.  Only keys in the allowlist with non-blank values
   * are included.
   *
   * AdminJS stores each filter entry as a FilterElement:
   *   { path: string, property: BaseProperty, value: string | {from, to}, populated? }
   * NOT as a raw string. We extract `.value` before building query params.
   *
   * Range filters (value = {from, to}) are split into two separate params using
   * the key suffixed with the companion key from filterKeys (e.g. from_ts/to_ts).
   */
  private _buildQueryString(filter: Filter): string {
    const allowedKeys = this.config.filterKeys ?? [];
    if (allowedKeys.length === 0) return "";

    // AdminJS Filter stores the active values in `.filters` as FilterElement objects.
    type FilterElement = { path: string; property: unknown; value: string | { from: string; to: string }; populated?: unknown };
    const rawFilters = (filter as unknown as { filters?: Record<string, FilterElement> }).filters ?? {};

    const params = new URLSearchParams();
    for (const key of allowedKeys) {
      const element = rawFilters[key];
      if (element === undefined || element === null) continue;

      const value = element.value;
      if (value === undefined || value === null) continue;

      // Range shape: { from, to } — split into from_<key> and to_<key> equivalents.
      // For from_ts/to_ts specifically: a single from_ts entry with {from, to} shape
      // maps to from_ts=<from> and to_ts=<to>.
      if (typeof value === "object" && "from" in value && "to" in value) {
        const { from, to } = value;
        if (from && typeof from === "string" && from.trim() !== "") {
          params.set(key, from.trim());
        }
        // Derive companion key: from_ts → to_ts, from_X → to_X, otherwise key + "_to"
        const companionKey = key.startsWith("from_")
          ? key.replace(/^from_/, "to_")
          : allowedKeys.find((k) => k.startsWith("to_") && k.slice(3) === key.slice(5)) ?? `${key}_to`;
        if (to && typeof to === "string" && to.trim() !== "" && allowedKeys.includes(companionKey)) {
          params.set(companionKey, to.trim());
        }
        continue;
      }

      // Scalar string value
      if (typeof value === "string") {
        const trimmed = value.trim();
        if (trimmed !== "") {
          params.set(key, trimmed);
        }
        continue;
      }

      // Numeric / boolean fallback
      const strVal = String(value);
      if (strVal !== "") {
        params.set(key, strVal);
      }
    }
    return params.toString();
  }

  async findOne(id: string, context?: ActionContext): Promise<BaseRecord | null> {
    const tenantId = (context?.currentAdmin as { tenantId?: string } | undefined)?.tenantId;
    if (!tenantId) return null;

    if (this.config.getPath) {
      const url = `${this.apiUrl}${this.config.getPath
        .replace("{tenantId}", tenantId)
        .replace("{id}", id)}`;
      try {
        const resp = await fetch(url, { headers: this._sessionHeaders(context) });
        if (!resp.ok) return null;
        const item = await resp.json() as Record<string, unknown>;
        return new BaseRecord(item, this);
      } catch {
        return null;
      }
    }

    // Fall back to finding from list
    const all = await this.find({} as Filter, {}, context);
    const idField = this.config.idField ?? "id";
    return all.find((r) => String(r.get(idField)) === id) ?? null;
  }

  async findMany(ids: Array<string | number>, context?: ActionContext): Promise<BaseRecord[]> {
    const results = await Promise.all(ids.map((id) => this.findOne(String(id), context)));
    return results.filter((r): r is BaseRecord => r !== null);
  }

  async count(_filter: Filter, context?: ActionContext): Promise<number> {
    const all = await this.find({} as Filter, {}, context);
    return all.length;
  }

  async create(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    return params;
  }

  async update(id: string, params: Record<string, unknown>): Promise<Record<string, unknown>> {
    return { id, ...params };
  }

  async delete(_id: string): Promise<void> {
    // no-op — custom actions handle deletes via admin-api
  }
}
