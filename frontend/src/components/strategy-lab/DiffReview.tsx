import { useMemo } from "react";

interface DiffReviewProps {
  diff: string;
  summary: string;
  onAccept: () => void;
  onReject: () => void;
  isApplying?: boolean;
}

interface ParsedLine {
  type: "context" | "add" | "remove";
  text: string;
  oldNum?: number;
  newNum?: number;
}

/**
 * Simple unified-diff renderer: parses hunk lines and shows them as a
 * stacked view with green/red color coding. No per-line accept/reject —
 * the user accepts the whole diff or rejects it (per Q23 in the plan).
 */
export function DiffReview({ diff, summary, onAccept, onReject, isApplying }: DiffReviewProps) {
  const lines = useMemo(() => parseDiffLines(diff), [diff]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-zinc-400">
          <span className="font-mono">{summary}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onReject}
            disabled={isApplying}
            className="rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={onAccept}
            disabled={isApplying}
            className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
          >
            {isApplying ? "Applying..." : "Accept changes"}
          </button>
        </div>
      </div>

      <div className="max-h-96 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 font-mono text-xs">
        {lines.length === 0 ? (
          <div className="p-4 text-zinc-500">No changes parsed.</div>
        ) : (
          lines.map((l, i) => (
            <div
              key={i}
              className={
                l.type === "add"
                  ? "bg-emerald-950/50 text-emerald-300"
                  : l.type === "remove"
                    ? "bg-red-950/50 text-red-300"
                    : "text-zinc-400"
              }
            >
              <span className="inline-block w-8 select-none text-right text-zinc-600">
                {l.oldNum ?? ""}
              </span>
              <span className="inline-block w-8 select-none text-right text-zinc-600">
                {l.newNum ?? ""}
              </span>
              <span className="ml-2">
                {l.type === "add" ? "+" : l.type === "remove" ? "-" : " "} {l.text}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function parseDiffLines(diff: string): ParsedLine[] {
  const out: ParsedLine[] = [];
  const lines = diff.split("\n");
  let oldNum = 0;
  let newNum = 0;
  let inHunk = false;

  for (const line of lines) {
    if (line.startsWith("---") || line.startsWith("+++")) {
      continue;
    }
    const hunkMatch = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunkMatch) {
      oldNum = parseInt(hunkMatch[1], 10);
      newNum = parseInt(hunkMatch[2], 10);
      inHunk = true;
      continue;
    }
    if (!inHunk) continue;
    if (line.startsWith("+")) {
      out.push({ type: "add", text: line.slice(1), newNum });
      newNum += 1;
    } else if (line.startsWith("-")) {
      out.push({ type: "remove", text: line.slice(1), oldNum });
      oldNum += 1;
    } else if (line.startsWith(" ")) {
      out.push({ type: "context", text: line.slice(1), oldNum, newNum });
      oldNum += 1;
      newNum += 1;
    }
  }
  return out;
}
