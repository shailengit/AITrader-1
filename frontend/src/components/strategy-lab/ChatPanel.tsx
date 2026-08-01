import { useState, useEffect, useRef } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, RefreshCw, AlertCircle, MessageSquare, Wand2, Save, RotateCcw } from "lucide-react";
import { strategyLabApi, type ChatMessage } from "../../lib/strategyLab";

interface ChatPanelProps {
  sessionId: string;
  defaultModelId: string;
  onReRun?: () => void;
}

export function ChatPanel({ sessionId, defaultModelId, onReRun }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [selectedModel, setSelectedModel] = useState(defaultModelId);
  const [critiquingId, setCritiquingId] = useState<string | null>(null);
  const [critiqueModel, setCritiqueModel] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [applyingInstruction, setApplyingInstruction] = useState<string | null>(null);
  const [applyTimer, setApplyTimer] = useState(0);
  const lastCodeChangeInstruction = useRef<string | null>(null);
  const [pendingSave, setPendingSave] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState(sessionId ? `strategy-${sessionId.slice(0, 8)}` : "strategy");
  const [saveDescription, setSaveDescription] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  // Load available models for the dropdown
  useEffect(() => {
    strategyLabApi.listModels().then((models) => {
      const flat: string[] = [];
      for (const m of models) {
        for (const v of m.variants) {
          flat.push(`${m.id}:${v.name}`);
        }
      }
      flat.sort();
      setModelOptions(flat);
    }).catch(() => {});
  }, []);

  // Load existing chat history
  const { data: history } = useQuery({
    queryKey: ["chat-history", sessionId],
    queryFn: () => strategyLabApi.getChatHistory(sessionId),
  });
  useEffect(() => {
    if (history) setMessages(history);
  }, [history]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  // Live timer for apply in progress
  useEffect(() => {
    if (!applyingInstruction) return;
    const startedAt = Date.now();
    setApplyTimer(0);
    const id = setInterval(() => setApplyTimer(Math.floor((Date.now() - startedAt) / 1000)), 250);
    return () => clearInterval(id);
  }, [applyingInstruction]);

  const send = useMutation({
    mutationFn: (body: { message: string; model: string; critique_of?: string }) =>
      strategyLabApi.chat(sessionId, body),
    onSuccess: (r) => {
      setMessages(r.history);
      // If the response has a code_change_instruction, we don't auto-apply —
      // the "Apply change" button lets the user decide.
    },
  });

  const applyChange = useMutation({
    mutationFn: (instruction: string) =>
      strategyLabApi.refineDirect(sessionId, {
        instruction,
        model: selectedModel,
        validation_runs: 10,
      }),
    onSuccess: (r) => {
      setApplyingInstruction(null);
      setApplyTimer(0);

      // Auto-save to library
      const changeDesc = lastCodeChangeInstruction.current || "AI-suggested improvement";
      saveToLib.mutate({
        name: `strategy-${sessionId.slice(0, 8)}-v${Date.now()}`,
        change_description: changeDesc,
      });

      const statusMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: r.validation_status === "passed"
          ? `✅ Change applied and verified with backtest runs.`
          : `⚠️ Change applied but some validation runs failed (${r.validation_status}).`,
        model_id: "system",
        critique_of: undefined,
        code_change_instruction: undefined,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, statusMsg]);
      setPendingSave(true);
    },
    onError: (e) => {
      setApplyingInstruction(null);
      setApplyTimer(0);
      const errMsg = extractErrorMessage(e);
      const statusMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `❌ Failed to apply change: ${errMsg}`,
        model_id: "system",
        critique_of: undefined,
        code_change_instruction: undefined,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, statusMsg]);
    },
  });

  const saveToLib = useMutation({
    mutationFn: (body: { name: string; change_description: string }) =>
      strategyLabApi.saveToLibrary(sessionId, body),
    onSuccess: () => {
      setSaveDialogOpen(false);
      setPendingSave(false);
      setSaveDescription("");
      const statusMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `✅ Saved to library as "${saveName}".`,
        model_id: "system",
        critique_of: undefined,
        code_change_instruction: undefined,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, statusMsg]);
    },
    onError: (e) => {
      const errMsg = extractErrorMessage(e);
      const statusMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `❌ Failed to save to library: ${errMsg}`,
        model_id: "system",
        critique_of: undefined,
        code_change_instruction: undefined,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, statusMsg]);
    },
  });

  const handleSend = () => {
    if (!input.trim() || send.isPending) return;
    const msg = input.trim();

    // Check for natural language approval of a pending code change
    const approvalKeywords = ["yes", "apply", "make the change", "do it", "go ahead", "sure", "please do"];
    const lastBotWithChange = [...messages].reverse().find(
      (m) => m.role === "assistant" && m.code_change_instruction
    );
    if (lastBotWithChange && approvalKeywords.some(k => msg.toLowerCase().includes(k))) {
      // Auto-trigger apply
      setApplyingInstruction(lastBotWithChange.code_change_instruction!);
      applyChange.mutate(lastBotWithChange.code_change_instruction!);
    }

    // Always send the message to chat
    send.mutate({ message: msg, model: selectedModel });
    setInput("");
  };

  const handleCritique = () => {
    if (!critiquingId || !critiqueModel) return;
    const critiquedIdx = messages.findIndex((m) => m.id === critiquingId);
    const userMsg = critiquedIdx > 0 ? messages[critiquedIdx - 1] : null;
    const critiquePrompt = userMsg
      ? `Critique the following analysis. The original question was: "${userMsg.content}"\n\nAnalysis to critique:\n${messages.find((m) => m.id === critiquingId)?.content ?? ""}`
      : `Critique the following analysis:\n${messages.find((m) => m.id === critiquingId)?.content ?? ""}`;
    send.mutate({ message: critiquePrompt, model: critiqueModel, critique_of: critiquingId });
    setCritiquingId(null);
    setCritiqueModel("");
  };

  return (
    <div className="slab-panel" style={{ maxWidth: 1280, marginTop: 24 }}>
      <div className="slab-panel__head">
        <span className="slab-eyebrow slab-eyebrow--gold">
          <MessageSquare size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
          Performance Chat
        </span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">
          ask about any run, compare, or get recommendations
        </span>
      </div>

      <div
        ref={listRef}
        style={{
          maxHeight: "calc(100vh - 320px)",
          minHeight: 200,
          overflowY: "auto",
          padding: "16px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {messages.length === 0 && !send.isPending && (
          <div style={{ textAlign: "center", padding: "32px 16px", color: "var(--slab-paper-faint)" }}>
            <MessageSquare size={24} style={{ marginBottom: 8, opacity: 0.4 }} />
            <p className="slab-prose" style={{ fontSize: 14 }}>
              Ask about performance — e.g. "why did run 3 underperform?" or "add a SPY {'>'} 20d MA filter"
            </p>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "80%",
                  padding: "10px 14px",
                  borderRadius: 8,
                  background: msg.role === "user"
                    ? "var(--slab-gold)"
                    : "var(--slab-ink-3)",
                  color: msg.role === "user" ? "var(--slab-ink-1)" : "var(--slab-paper)",
                  fontSize: 13,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {msg.content}
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginTop: 4,
                  fontSize: 11,
                  color: "var(--slab-paper-faint)",
                }}
              >
                {msg.role === "assistant" && (
                  <>
                    <Bot size={10} />
                    <span className="slab-mono slab-mono--xs">{msg.model_id || "unknown"}</span>
                    {msg.critique_of && (
                      <span style={{ color: "var(--slab-cyan)" }}>· critique</span>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setCritiquingId(msg.id);
                        setCritiqueModel("");
                      }}
                      className="slab-btn slab-btn--xs slab-btn--ghost"
                      style={{ fontSize: 10, padding: "2px 6px" }}
                    >
                      Critique
                    </button>
                  </>
                )}
                {msg.role === "user" && (
                  <>
                    <User size={10} />
                    <span className="slab-mono slab-mono--xs">{msg.model_id || "you"}</span>
                  </>
                )}
              </div>

              {/* Inline critique model picker */}
              {critiquingId === msg.id && msg.role === "assistant" && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}
                >
                  <span className="slab-mono slab-mono--xs" style={{ color: "var(--slab-paper-faint)" }}>
                    Critique with:
                  </span>
                  <select
                    value={critiqueModel}
                    onChange={(e) => setCritiqueModel(e.target.value)}
                    className="slab-input"
                    style={{ width: 180, fontSize: 11, padding: "4px 6px" }}
                  >
                    <option value="">Select model…</option>
                    {modelOptions.filter((m) => m !== selectedModel).map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={handleCritique}
                    disabled={!critiqueModel || send.isPending}
                    className="slab-btn slab-btn--xs"
                  >
                    {send.isPending ? "..." : "Go"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setCritiquingId(null)}
                    className="slab-btn slab-btn--xs slab-btn--ghost"
                  >
                    Cancel
                  </button>
                </motion.div>
              )}

              {/* Apply change button — shown on bot messages that contain a code_change_instruction */}
              {msg.code_change_instruction && (
                <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                  {applyingInstruction === msg.code_change_instruction ? (
                    <span className="slab-status slab-status--live">
                      <span className="slab-status__dot" />
                      Applying change
                      <span className="slab-mono slab-mono--xs slab-mono--dim" style={{ marginLeft: 8 }}>
                        {applyTimer}s
                      </span>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setApplyingInstruction(msg.code_change_instruction!);
                        lastCodeChangeInstruction.current = msg.code_change_instruction!;
                        applyChange.mutate(msg.code_change_instruction!);
                      }}
                      disabled={applyChange.isPending}
                      className="slab-btn slab-btn--sm slab-btn--primary"
                    >
                      <Wand2 size={10} /> Apply change
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {send.isPending && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
            <span className="slab-status slab-status--live">
              <span className="slab-status__dot" />
              Thinking
            </span>
            <span className="slab-mono slab-mono--xs slab-mono--dim">{selectedModel}</span>
          </div>
        )}

        {send.isError && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
            <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <AlertCircle size={12} />
              {String((send.error as Error)?.message ?? "Chat failed")}
            </span>
            <button type="button" onClick={() => send.mutate({ message: input, model: selectedModel })} className="slab-btn slab-btn--xs">
              <RefreshCw size={10} /> Retry
            </button>
          </div>
        )}

        {/* Save to library prompt — shown after a successful apply */}
        {pendingSave && !saveDialogOpen && (
          <div style={{ display: "flex", gap: 8, padding: "8px 0", borderTop: "1px solid var(--slab-rule)", marginTop: 8 }}>
            <button
              type="button"
              onClick={() => setSaveDialogOpen(true)}
              className="slab-btn slab-btn--sm slab-btn--terminal"
            >
              <Save size={10} /> Save to library
            </button>
            {onReRun && (
              <button
                type="button"
                onClick={onReRun}
                className="slab-btn slab-btn--sm slab-btn--primary"
              >
                <RotateCcw size={10} /> Re-run with same dates
              </button>
            )}
            <button
              type="button"
              onClick={() => setPendingSave(false)}
              className="slab-btn slab-btn--sm slab-btn--ghost"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Save dialog */}
        {saveDialogOpen && (
          <div style={{ padding: "12px 0", borderTop: "1px solid var(--slab-rule)", marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="slab-eyebrow slab-eyebrow--gold" style={{ fontSize: 11 }}>// Save to library</span>
            <input
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Strategy name"
              className="slab-input"
              style={{ fontSize: 13 }}
            />
            <input
              type="text"
              value={saveDescription}
              onChange={(e) => setSaveDescription(e.target.value)}
              placeholder="What changed?"
              className="slab-input"
              style={{ fontSize: 13 }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                onClick={() => saveToLib.mutate({ name: saveName, change_description: saveDescription })}
                disabled={!saveName.trim() || saveToLib.isPending}
                className="slab-btn slab-btn--sm slab-btn--primary"
              >
                {saveToLib.isPending ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => setSaveDialogOpen(false)}
                className="slab-btn slab-btn--sm slab-btn--ghost"
              >
                Cancel
              </button>
              {saveToLib.isError && (
                <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <AlertCircle size={12} />
                  {extractErrorMessage(saveToLib.error)}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Input bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "12px 16px",
          borderTop: "1px solid var(--slab-rule)",
        }}
      >
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="slab-input"
          style={{ width: 180, fontSize: 11, padding: "6px 8px", flexShrink: 0 }}
          disabled={send.isPending}
        >
          {modelOptions.length === 0 && (
            <option value={selectedModel}>{selectedModel}</option>
          )}
          {modelOptions.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Ask about performance or suggest a code change..."
          className="slab-input"
          style={{ flex: 1, fontSize: 13 }}
          disabled={send.isPending}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!input.trim() || send.isPending}
          className="slab-btn slab-btn--primary"
          style={{ padding: "8px 12px" }}
        >
          <Send size={12} />
        </button>
      </div>
    </div>
  );
}

// Parse a FastAPI error response into a user-friendly string.
function extractErrorMessage(err: unknown): string {
  if (!err) return "Unknown error";
  const e = err as { message?: string; detail?: unknown };
  let d: unknown = e.detail;
  if (typeof d === "object" && d !== null && "detail" in (d as object)) {
    d = (d as { detail: unknown }).detail;
  }
  if (typeof d === "object" && d !== null) {
    const obj = d as { details?: string; error?: string };
    if (obj.details) return obj.details;
    if (obj.error) return obj.error;
  }
  if (typeof d === "string") return d;
  if (e.message) return e.message;
  return String(err);
}
