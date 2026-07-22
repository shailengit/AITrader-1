import { useMemo } from "react";
import { Check, X } from "lucide-react";

interface DiffReviewProps {
  diff: string;
  summary: string;
  onAccept: () => void;
  onReject: () => void;
  isApplying?: boolean;
}

interface ParsedLine {
  type: "context" | "add" | "remove" | "hunk";
  text: string;
  oldNum?: number;
  newNum?: number;
}

export function DiffReview({ diff, summary, onAccept, onReject, isApplying }: DiffReviewProps) {
  const lines = useMemo(() => parseDiffLines(diff), [diff]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="slab-eyebrow slab-eyebrow--gold">// Proposed diff</span>
          <span className="slab-mono slab-mono--sm slab-mono--dim">{summary}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            onClick={onReject}
            disabled={isApplying}
            className="slab-btn slab-btn--sm"
          >
            <X size={10} />
            Reject
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={isApplying}
            className="slab-btn slab-btn--sm slab-btn--primary"
          >
            <Check size={10} />
            {isApplying ? "Applying…" : "Accept"}
          </button>
        </div>
      </div>

      <div className="slab-diff">
        {lines.length === 0 ? (
          <div style={{ padding: 16, color: "var(--slab-paper-faint)" }} className="slab-mono slab-mono--sm">
            No changes parsed.
          </div>
        ) : (
          lines.map((l, i) => (
            <div
              key={i}
              className={
                l.type === "add"
                  ? "slab-diff__row slab-diff__row--add"
                  : l.type === "remove"
                    ? "slab-diff__row slab-diff__row--remove"
                    : l.type === "hunk"
                      ? "slab-diff__row slab-diff__row--hunk"
                      : "slab-diff__row"
              }
            >
              <span className="slab-diff__gutter">{l.oldNum ?? ""}</span>
              <span className="slab-diff__gutter">{l.newNum ?? ""}</span>
              <span className="slab-diff__text">
                {l.type === "add"
                  ? "+ "
                  : l.type === "remove"
                    ? "- "
                    : l.type === "hunk"
                      ? "@@ "
                      : "  "}
                {l.text}
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
    if (line.startsWith("---") || line.startsWith("+++")) continue;
    const hunkMatch = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunkMatch) {
      out.push({ type: "hunk", text: line });
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
