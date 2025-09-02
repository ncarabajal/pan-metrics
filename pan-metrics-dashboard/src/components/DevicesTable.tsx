import { useQuery } from "@tanstack/react-query";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import { fetchJSON } from "../api";

/** We render whatever keys the API returns (base + extras). */
type Device = Record<string, unknown>;

/* ────── thresholds (tweak if you like) ────── */
const CERT_YELLOW_DAYS = 60;
const CERT_RED_DAYS = 30;
const CPU_YELLOW = 70;
const CPU_RED = 90;
const MEM_YELLOW = 80;
const MEM_RED = 90;
const SWAP_YELLOW_MIB = 512;
const SWAP_RED_MIB = 1024;
const PCT_YELLOW = 85;
const PCT_GREEN = 70;

/* ────── helpers ────── */
const isNum = (v: unknown): v is number => typeof v === "number" && !Number.isNaN(v);
const asNum = (v: unknown): number | null =>
  (isNum(v) ? v : v == null || v === "" ? null : Number(v));
const toPct = (n: number | null) => (n == null ? "" : `${Math.round(n)}%`);
const pretty = (k: string) =>
  (LABELS[k] ?? k).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Friendly labels for some columns */
const LABELS: Record<string, string> = {
  hostname: "Hostname",
  serial: "Serial",
  ip: "IP",
  connected: "Connected",
  ha_state: "HA",
  panorama: "Panorama",
  timestamp: "Snapshot",
  pan_os_version: "PAN-OS",
  model: "Model",
  cpu_one_min: "CPU (1-min)",
  memory_usage: "Memory %",
  swap_used: "Swap (MiB)",
  session_count: "Sessions (active)",
  session_max: "Sessions (max)",
  logging_service: "Logging Service",
  device_certificate: "Device Cert",
  device_cert_exp: "Device Cert Exp",
  device_cert_days: "Device Cert Days",
  status_device_certificate: "Status: Device Cert",
  status_device_certificate_expiry_date: "Status: Cert Exp",
};

/** Pinned order first; any new/unknown fields will be appended after these */
const PINNED_ORDER = [
  "hostname",
  "serial",
  "ip",
  "connected",
  "ha_state",
  "panorama",
  "timestamp",
  "pan_os_version",
  "model",

  "cpu_one_min",
  "memory_usage",
  "swap_used",

  "session_count",
  "session_max",

  "logging_service",
  "device_certificate",
  "device_cert_exp",
  "device_cert_days",
  "status_device_certificate",
  "status_device_certificate_expiry_date",

  // common disk keys often present
  "disk_root_pct",
  "disk_dev_pct",
  "disk_opt_pancfg_pct",
  "disk_opt_panrepo_pct",
  "disk_dev_shm_pct",
  "disk_cgroup_pct",
  "disk_opt_panlogs_pct",
  "disk_opt_pancfg_mgmt_ssl_private_pct",
  "disk_opt_panraid_ld1_pct",

  // resource-monitor rollups (if present)
  "pktbuf_avg_hour_pct",
  "pktbuf_max_hour_pct",
  "pktdesc_avg_hour_pct",
  "pktdesc_max_hour_pct",
  "pktdesc_onchip_avg_hour_pct",
  "pktdesc_onchip_max_hour_pct",
  "session_avg_hour_pct",
  "session_max_hour_pct",
  "dp_cpu_max_hour_pct",
];

/** Colour rules per key family */
const GREEN = "#16a34a";
const YELLOW = "#ca8a04";
const RED = "#dc2626";

/** parse either ISO like "2025-08-29T18:00:00Z" or PAN-OS style "YYYY/MM/DD HH:MM:SS UTC" */
function daysUntil(dateStr: string): number | null {
  if (!dateStr) return null;
  // try ISO first
  const iso = new Date(dateStr);
  if (!Number.isNaN(iso.getTime())) {
    return Math.floor((iso.getTime() - Date.now()) / 86400000);
  }
  // try PAN-OS format
  const m = dateStr.match(/^(\d{4})\/(\d{2})\/(\d{2}) (\d{2}):(\d{2}):(\d{2}) UTC$/);
  if (m) {
    const d = new Date(
      Number(m[1]),
      Number(m[2]) - 1,
      Number(m[3]),
      Number(m[4]),
      Number(m[5]),
      Number(m[6])
    );
    return Math.floor((d.getTime() - Date.now()) / 86400000);
  }
  return null;
}

function isTruthyYes(v: unknown) {
  const s = String(v ?? "").trim().toLowerCase();
  return ["yes", "true", "valid", "ok", "installed"].some((w) => s.includes(w));
}
function isWarnish(v: unknown) {
  const s = String(v ?? "").trim().toLowerCase();
  return ["warn", "warning", "expiring", "syncing", "pending", "degraded", "partial"].some((w) =>
    s.includes(w)
  );
}
function isBadNo(v: unknown) {
  const s = String(v ?? "").trim().toLowerCase();
  return ["no", "false", "error", "failed", "down", "expired", "invalid", "missing"].some((w) =>
    s.includes(w)
  );
}

function colour(key: string, value: unknown, row: Device): string {
  // Simple flags
  if (key === "connected" || key === "logging_service") {
    return isTruthyYes(value) ? GREEN : RED;
  }

  // HA: active=green, passive=yellow, suspended/error=red
  if (key === "ha_state") {
    const s = String(value ?? "").toLowerCase();
    if (s.includes("active")) return GREEN;
    if (s.includes("passive")) return YELLOW;
    if (s.includes("suspend") || s.includes("error") || s.includes("non-functional")) return RED;
    return "";
  }

  // Device certificate (string status)
  if (key === "device_certificate" || key === "status_device_certificate") {
    if (isBadNo(value)) return RED;
    if (isWarnish(value)) return YELLOW;
    if (isTruthyYes(value)) return GREEN;
    return "";
  }

  // Device certificate expiry (date string)
  if (key === "device_cert_exp" || key === "status_device_certificate_expiry_date") {
    const days = typeof value === "string" ? daysUntil(value) : null;
    if (days == null) return "";
    if (days < CERT_RED_DAYS) return RED;
    if (days < CERT_YELLOW_DAYS) return YELLOW;
    return "";
  }

  // Device certificate days remaining (numeric)
  if (key === "device_cert_days") {
    const n = asNum(value);
    if (n == null) return "";
    if (n < CERT_RED_DAYS) return RED;
    if (n < CERT_YELLOW_DAYS) return YELLOW;
    return GREEN;
  }

  const num = asNum(value);
  if (num == null) {
    // Generic textual "status_*" fields
    if (key.startsWith("status_")) {
      if (isBadNo(value)) return RED;
      if (isWarnish(value)) return YELLOW;
      if (isTruthyYes(value)) return GREEN;
    }
    return "";
  }

  // Session utilization (active vs max)
  if (key === "session_count") {
    const max = asNum(row["session_max"]);
    if (!max) return "";
    const ratio = (100 * num) / max;
    return ratio < 60 ? GREEN : ratio <= 80 ? YELLOW : RED;
  }

  // CPU / Mem / Swap
  if (key === "cpu_one_min") return num < CPU_YELLOW ? GREEN : num <= CPU_RED ? YELLOW : RED;
  if (key === "memory_usage") return num < MEM_YELLOW ? GREEN : num <= MEM_RED ? YELLOW : RED;
  if (key === "swap_used")
    return num < SWAP_YELLOW_MIB ? GREEN : num <= SWAP_RED_MIB ? YELLOW : RED;

  // Generic % metrics (anything ending with "_pct")
  if (/_pct$/.test(key)) return num < PCT_GREEN ? GREEN : num <= PCT_YELLOW ? YELLOW : RED;

  // Heuristics for hourly max/avg metrics commonly added (pktbuf/pktdesc/session/dp_cpu)
  if (
    /^(dp_cpu_max_hour_pct|mp_cpu_max_hour_pct|session_avg_hour_pct|session_max_hour_pct|pktbuf_|pktdesc_)/.test(
      key
    )
  ) {
    return num < PCT_GREEN ? GREEN : num <= PCT_YELLOW ? YELLOW : RED;
  }

  // Everything else numeric: no colour
  return "";
}

function renderValue(key: string, value: unknown, row: Device) {
  // Date-ish fields → append (Xd)
  if (key === "device_cert_exp" || key === "status_device_certificate_expiry_date") {
    if (typeof value === "string") {
      const days = daysUntil(value);
      return days == null ? value : `${value} (${days}d)`;
    }
  }

  // Numeric "days remaining"
  if (key === "device_cert_days") {
    const n = asNum(value);
    return n == null ? "" : `${Math.round(n)}d`;
  }

  // Percentages
  if (/_pct$/.test(key)) return toPct(asNum(value));

  // Session count shown with utilization if we can compute it
  if (key === "session_count") {
    const v = asNum(value);
    const max = asNum(row["session_max"]);
    if (v == null) return "";
    if (max) {
      const pct = Math.round((100 * v) / max);
      return `${v} (${pct}%)`;
    }
    return String(v);
  }

  // Memory already in %, CPU load value, Swap MiB → format
  if (key === "cpu_one_min" || key === "memory_usage" || key === "swap_used") {
    const v = asNum(value);
    return v == null ? "" : key === "memory_usage" ? `${v.toFixed(0)}%` : v.toFixed(2);
  }

  if (isNum(value)) return (value as number).toFixed(2);
  if (value == null) return "";
  return String(value);
}

/* ────── React component ────── */
export default function DevicesTable() {
  const { data = [], isLoading } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => fetchJSON<Device[]>("/devices"),
    refetchInterval: 60_000,
  });

  // Compute the union of keys across all rows
  const allKeys = Array.from(new Set(data.flatMap((r) => Object.keys(r ?? {}))));

  // Build final column order: pinned first (when present), then everything else alphabetically
  const seen = new Set<string>();
  const orderedKeys = [
    ...PINNED_ORDER.filter((k) => allKeys.includes(k)),
    ...allKeys.filter((k) => !seen.has(k) && !PINNED_ORDER.includes(k)).sort(),
  ].filter((k) => (seen.has(k) ? false : (seen.add(k), true)));

  const columns: ColumnDef<Device>[] = orderedKeys.map((key) => ({
    accessorKey: key,
    header: pretty(key),
    cell: (ctx) => {
      const row = ctx.row.original as Device;
      const val = ctx.getValue<unknown>();
      const color = colour(key, val, row);
      return (
        <span style={color ? { color, fontWeight: 600 } : undefined}>
          {renderValue(key, val, row)}
        </span>
      );
    },
  }));

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) return <p style={{ padding: "1rem" }}>Loading…</p>;
  if (data.length === 0) return <p style={{ padding: "1rem" }}>No devices found.</p>;

  const cellBorder = { border: "1px solid #d1d5db" };

  return (
    <div style={{ maxHeight: "70vh", overflow: "auto" }}>
      <table style={{ minWidth: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  style={{
                    ...cellBorder,
                    position: "sticky",
                    top: 0,
                    background: "#f3f4f6",
                    zIndex: 2,
                    padding: "0.5rem 0.75rem",
                    textAlign: "left",
                    whiteSpace: "normal",
                    lineHeight: 1.25,
                    fontWeight: 700,
                  }}
                >
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} style={{ background: row.index % 2 ? "#fafafa" : "white" }}>
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  style={{
                    ...cellBorder,
                    padding: "0.25rem 0.75rem",
                    whiteSpace: "nowrap",
                  }}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
