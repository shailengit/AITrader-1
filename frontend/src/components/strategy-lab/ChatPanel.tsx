import { useState, useEffect, useRef } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, RefreshCw, AlertCircle, MessageSquare } from "lucide-react";
import { strategyLabApi, type ChatMessage } from "../../lib/strategyLab";
import { ModelPicker } from "../../pages/StrategyLab/StepIdea";

interface ChatPanelProps {
  sessionId: string;
  defaultModelId: string;
}

export function ChatPanel({ sessionId, defaultModelId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [selectedModel, setSelectedModel] = useState(defaultModelId);
  const [critiquingId, setCritiquingId] = useState<string | null>(null);
  const [critiqueModel, setCritiqueModel] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

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

  const send = useMutation({
    mutationFn: (body: { message: string; model: string; critique_of?: string }) =>
      strategyLabApi.chat(sessionId, body),
    onSuccess: (r) => setMessages(r.history),
  });

  const handleSend = () => {
    if (!input.trim() || send.isPending) return;
    send.mutate({ message: input.trim(), model: selectedModel });
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
          maxHeight: 400,
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
              Ask about performance — e.g. "why did run 3 underperform?" or "what do the worst runs have in common?"
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
                  <ModelPicker value={critiqueModel} onChange={setCritiqueModel} />
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
          style={{ width: 160, fontSize: 11, padding: "6px 8px", flexShrink: 0 }}
          disabled={send.isPending}
        >
          <option value={selectedModel}>{selectedModel}</option>
        </select>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Ask about performance..."
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
