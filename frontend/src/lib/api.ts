import type {
  Detail,
  HitMeta,
  HitRuleDetail,
  HitRuleRow,
  Filters,
  JobSnapshot,
  Meta,
  ObjectDetail,
  ObjectSummary,
  OrderChange,
  ParseWarning,
  RecentProject,
  Row,
  Settings,
  UnresolvedRef,
  UploadInfo,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Sibit's local server is not reachable. Is Sibit still running?");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : msg;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function filtersToParams(f: Partial<Filters>): URLSearchParams {
  const p = new URLSearchParams();
  if (f.status?.length) p.set("status", f.status.join(","));
  if (f.severity?.length) p.set("severity", f.severity.join(","));
  if (f.acl?.length) p.set("acl", f.acl.join(","));
  if (f.flag?.length) p.set("flag", f.flag.join(","));
  if (f.enabled) p.set("enabled", f.enabled);
  if (f.q?.trim()) p.set("q", f.q.trim());
  return p;
}

/** Upload with progress (XHR, since fetch has no upload progress). */
export function uploadFile(kind: "asa" | "ftd" | "hits", file: File, onProgress?: (pct: number) => void): Promise<UploadInfo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    xhr.open("POST", "/api/uploads");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((100 * e.loaded) / e.total));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else {
        let msg = "Upload failed";
        try {
          msg = JSON.parse(xhr.responseText).detail ?? msg;
        } catch {
          /* ignore */
        }
        reject(new ApiError(xhr.status, msg));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Upload failed — is Sibit still running?"));
    xhr.send(fd);
  });
}

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/api/health"),
  deleteUpload: (id: string) => request<{ ok: boolean }>(`/api/uploads/${id}`, { method: "DELETE" }),
  startJob: (body: {
    asa_upload: string;
    ftd_upload: string;
    numbering: string;
    include_disabled: boolean;
    ignore_comments: boolean;
  }) => request<JobSnapshot>("/api/jobs", json("POST", body)),
  job: (id: string) => request<JobSnapshot>(`/api/jobs/${id}`),
  cancelJob: (id: string) => request<{ ok: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  jobEventsUrl: (id: string) => `/api/jobs/${id}/events`,

  sessions: () =>
    request<{ id: string; name: string; created: string; asa_name: string; ftd_name: string; saved_path: string | null }[]>(
      "/api/sessions",
    ),
  meta: (sid: string) => request<Meta>(`/api/sessions/${sid}/meta`),
  rename: (sid: string, name: string) => request<{ name: string }>(`/api/sessions/${sid}`, json("PATCH", { name })),
  rows: (sid: string) => request<Row[]>(`/api/sessions/${sid}/rows`),
  rule: (sid: string, id: number) => request<Detail>(`/api/sessions/${sid}/rules/${id}`),
  search: (sid: string, f: Partial<Filters>) =>
    request<{ ids: number[]; total: number }>(`/api/sessions/${sid}/search?${filtersToParams(f)}`),
  order: (sid: string) => request<OrderChange[]>(`/api/sessions/${sid}/order`),
  warnings: (sid: string) =>
    request<{ warnings: ParseWarning[]; unresolved: UnresolvedRef[] }>(`/api/sessions/${sid}/warnings`),
  objects: (sid: string, q: string, side: string) => {
    const p = new URLSearchParams({ limit: "2000" });
    if (q.trim()) p.set("q", q.trim());
    if (side) p.set("side", side);
    return request<{ total: number; items: ObjectSummary[] }>(`/api/sessions/${sid}/objects?${p}`);
  },
  object: (sid: string, side: string, name: string) =>
    request<ObjectDetail>(`/api/sessions/${sid}/object?${new URLSearchParams({ side, name })}`),
  exportUrl: (sid: string, format: "xlsx" | "csv" | "json", filters?: Partial<Filters>) => {
    const p = filters ? filtersToParams(filters) : new URLSearchParams();
    p.set("format", format);
    if (filters) p.set("filtered", "true");
    return `/api/sessions/${sid}/export?${p}`;
  },
  save: (sid: string, name?: string) => request<{ path: string }>(`/api/sessions/${sid}/save`, json("POST", { name })),
  projectUrl: (sid: string) => `/api/sessions/${sid}/project`,
  recent: () => request<RecentProject[]>("/api/projects/recent"),
  openProject: (path: string) =>
    request<{ session_id: string; name: string }>("/api/projects/open", json("POST", { path })),
  uploadProject: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ session_id: string; name: string }>("/api/projects/upload", { method: "POST", body: fd });
  },
  settings: () => request<Settings>("/api/settings"),
  saveSettings: (patch: Partial<Settings>) => request<Settings>("/api/settings", json("PUT", patch)),
  shutdown: () => request<{ ok: boolean }>("/api/shutdown", { method: "POST" }),

  // hit counts
  startHits: (upload: string) => request<JobSnapshot>("/api/hits/jobs", json("POST", { upload })),
  hitsMeta: (hid: string) => request<HitMeta>(`/api/hits/${hid}/meta`),
  hitsRules: (hid: string, p: { verdict: string; q: string; sort: string; offset: number; limit: number }) =>
    request<{ total: number; offset: number; rows: HitRuleRow[] }>(
      `/api/hits/${hid}/rules?${new URLSearchParams({ ...p, offset: String(p.offset), limit: String(p.limit) })}`,
    ),
  hitsRule: (hid: string, id: number) => request<HitRuleDetail>(`/api/hits/${hid}/rules/${id}`),
  hitsExportUrl: (hid: string, format: "xlsx" | "csv", verdict = "", q = "") =>
    `/api/hits/${hid}/export?${new URLSearchParams({ format, verdict, q })}`,
};
