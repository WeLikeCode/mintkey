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
    const admin = context?.currentAdmin as { sessionToken?: string } | undefined;
    const tok = admin?.sessionToken;
    return tok ? { Cookie: `mintkey_session=${tok}` } : {};
  }

  async find(
    _filter: Filter,
    _options: { limit?: number; offset?: number; sort?: { sortBy?: string; direction?: "asc" | "desc" } },
    context?: ActionContext
  ): Promise<BaseRecord[]> {
    const tenantId = (context?.currentAdmin as { tenantId?: string } | undefined)?.tenantId;
    if (!tenantId) return [];

    const url = `${this.apiUrl}${this.config.listPath.replace("{tenantId}", tenantId)}`;
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
