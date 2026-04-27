import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import {
  Play,
  Save,
  Terminal,
  Activity,
  Trash2,
  Microscope,
  FilePlus,
  MessageCircle,
  Send,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from 'lucide-react';
import { OptimizationConfig } from '@/components/quantgen';
import { useTheme } from '../../context/ThemeContext';

const API_URL = '/api';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ParamRange {
  name: string;
  start: number;
  stop: number;
  step: number;
}

interface WFOConfig {
  type: 'rolling' | 'expanding';
  windows: number;
  ratio: number;
  splitMethod: 'ratio' | 'fixed';
  train_days: number;
  test_days: number;
  start_date: string;
  end_date: string;
}

interface OptimizationConfigData {
  mode: 'simple' | 'wfo' | 'true_wfo';
  metric: 'total_return' | 'sharpe' | 'sortino' | 'max_dd';
  wfo: WFOConfig;
}

// Default config
const defaultOptConfig: OptimizationConfigData = {
  mode: 'true_wfo',
  metric: 'total_return',
  wfo: {
    type: 'rolling',
    windows: 10,
    ratio: 0.7,
    splitMethod: 'ratio',
    train_days: 252,
    test_days: 63,
    start_date: '2023-01-01',
    end_date: '2024-01-01',
  },
};

export default function Builder() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isDarkMode } = useTheme();
  const fromScreenerTicker = searchParams.get('ticker');
  const [strategyPrompt, setStrategyPrompt] = useState('');
  const [tickers, setTickers] = useState(() => {
    // Pre-fill from AI Stock Screener if navigated with ?ticker=XYZ
    return fromScreenerTicker || 'AAPL';
  });
  const [code, setCode] = useState('');
  const [output, setOutput] = useState('');
  const [currentFilename, setCurrentFilename] = useState<string | null>(null);
  const isFirstLoad = useRef(true);

  const [isGenerating, setIsGenerating] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [strategies, setStrategies] = useState<string[]>([]);

  // Run mode
  const [runMode, setRunMode] = useState<'backtest' | 'optimize'>('backtest');
  const [optConfig, setOptConfig] = useState<OptimizationConfigData>(defaultOptConfig);
  const [optParams, setOptParams] = useState<ParamRange[]>([]);

  // Chat
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);

  // Theme-aware colors
  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? '#A1A1AA' : '#6e6e73',
    subtle: isDarkMode ? '#52525B' : '#86868b',
    surface: isDarkMode ? '#27272A' : '#ffffff',
    surfaceAlt: isDarkMode ? '#27272A' : '#f5f5f7',
    border: isDarkMode ? '#3F3F46' : '#d2d2d7',
    inputBg: isDarkMode ? '#18181B' : '#ffffff',
    codeBg: isDarkMode ? '#1E1E1E' : '#ffffff',
    consoleBg: isDarkMode ? '#09090B' : '#f5f5f7',
    consoleText: isDarkMode ? '#A1A1AA' : '#6e6e73',
    chatUserBg: isDarkMode ? '#10B981' : '#059669',
    chatAssistantBg: isDarkMode ? '#27272A' : '#e5e5e7',
    chatAssistantText: isDarkMode ? '#D4D4D8' : '#1d1d1f',
    accentBg: isDarkMode ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)',
    accentBorder: isDarkMode ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.3)',
  };

  // Load saved state
  useEffect(() => {
    if (!isFirstLoad.current) return;
    isFirstLoad.current = false;

    const saved = localStorage.getItem('builderState');
    if (saved) {
      try {
        const state = JSON.parse(saved);
        if (state.code) setCode(state.code);
        if (state.strategyPrompt) setStrategyPrompt(state.strategyPrompt);
        if (state.currentFilename) setCurrentFilename(state.currentFilename);
        if (state.runMode) setRunMode(state.runMode);
        if (state.optConfig) {
          setOptConfig({
            ...defaultOptConfig,
            ...state.optConfig,
            wfo: {
              ...defaultOptConfig.wfo,
              ...(state.optConfig.wfo || {}),
            },
          });
        }
        if (state.optParams) setOptParams(state.optParams);
        if (state.tickers) setTickers(state.tickers);
      } catch (e) {
        console.error('Failed to restore state:', e);
      }
    }
    loadStrategies();
  }, []);

  // Save state
  const saveState = useCallback(() => {
    const state = {
      code,
      strategyPrompt,
      currentFilename,
      runMode,
      optConfig,
      optParams,
      tickers,
    };
    localStorage.setItem('builderState', JSON.stringify(state));
  }, [code, strategyPrompt, currentFilename, runMode, optConfig, optParams, tickers]);

  useEffect(() => {
    if (!isFirstLoad.current) {
      saveState();
    }
  }, [saveState]);

  // Extract parameters from code
  useEffect(() => {
    if (!code) return;

    const lines = code.split('\n');
    let inParamsSection = false;
    const foundParams: { name: string; value: number }[] = [];

    for (const line of lines) {
      const trimmed = line.trim();
      if (
        trimmed.toLowerCase().startsWith('# parameters') ||
        trimmed.toLowerCase().startsWith('#parameters')
      ) {
        inParamsSection = true;
        continue;
      }

      if (inParamsSection) {
        if (!trimmed) continue;
        if (trimmed.startsWith('#')) continue;

        const match = trimmed.match(
          /^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([0-9.]+)(\s*#.*)?$/
        );
        if (match) {
          const val = parseFloat(match[2]);
          foundParams.push({
            name: match[1],
            value: isNaN(val) ? 10 : val,
          });
        } else {
          break;
        }
      }
    }

    if (foundParams.length > 0) {
      setOptParams((prev) => {
        const existingMap = new Map(prev.map((p) => [p.name, p]));

        const newParams = foundParams.map((p) => {
          if (existingMap.has(p.name)) {
            return existingMap.get(p.name)!;
          }
          const start = p.value;
          const stop = p.value * 2 || 100;
          const step = p.value >= 10 ? Math.floor(p.value / 10) : 1;

          return {
            name: p.name,
            start,
            stop,
            step: step || 1,
          };
        });

        if (JSON.stringify(newParams) === JSON.stringify(prev)) {
          return prev;
        }
        return newParams;
      });
    }
  }, [code]);

  const loadStrategies = async () => {
    try {
      const res = await fetch(`${API_URL}/strategies`);
      const data = await res.json();
      const list = data.data?.strategies || data.strategies || [];
      setStrategies(Array.isArray(list) ? list : []);
    } catch (e) {
      console.error('Failed to load strategies:', e);
    }
  };

  const handleGenerate = async () => {
    if (!strategyPrompt.trim()) return;
    setIsGenerating(true);

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: strategyPrompt,
          tickers: tickers.split(',').map((t) => t.trim()),
          start_date: '2020-01-01',
          end_date: '2024-01-01',
        }),
      });

      const data = await res.json();

      if (data.success && data.data?.code) {
        setCode(data.data.code);
        setOutput(data.data.output || 'Strategy generated successfully!');
      } else {
        const errorMsg = data.error?.message || data.error || 'Unknown error';
        setOutput(`GENERATION FAILED\n\nError: ${errorMsg}\n\nPartial Output:\n${data.data?.output || ''}`);
      }
    } catch (e: any) {
      setOutput(`API Error: ${e.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleRun = async () => {
    if (!code) return;
    setIsRunning(true);

    try {
      let endpoint = `${API_URL}/run`;
      let body: any = { code };

      if (runMode === 'optimize') {
        endpoint = `${API_URL}/optimize`;
        const strategy_params: Record<string, { start: number; stop: number; step: number }> = {};
        optParams.forEach((p) => {
          if (p.name) {
            strategy_params[p.name] = {
              start: p.start,
              stop: p.stop,
              step: p.step,
            };
          }
        });
        body = { code, strategy_params, config: optConfig };
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errorText || res.statusText}`);
      }

      const contentType = res.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await res.text();
        throw new Error(`Expected JSON but got ${contentType}: ${text.substring(0, 200)}`);
      }

      const data = await res.json();

      if (data.output) setOutput(data.output);
      if (data.data?.output) setOutput(data.data.output);
      if (data.error) {
        const errorMsg = data.error.message || data.error;
        setOutput((prev) => prev + `\n\nERROR:\n${errorMsg}`);
      }

      if (data.data?.stats || data.data?.best_equity || data.data?.equity || data.data?.windows) {
        // Truncate large arrays to avoid localStorage quota errors
        const maxEquityPoints = 1000;
        const maxTrades = 500;

        let equity = data.data.equity || [];
        let bestEquity = data.data.best_equity || [];
        let trades = data.data.trades || [];

        // Truncate if needed
        if (equity.length > maxEquityPoints) {
          equity = equity.slice(0, maxEquityPoints);
        }
        if (bestEquity.length > maxEquityPoints) {
          bestEquity = bestEquity.slice(0, maxEquityPoints);
        }
        if (trades.length > maxTrades) {
          trades = trades.slice(0, maxTrades);
        }

        // Always create optimization object for optimization runs
        const runData = {
          stats: data.data.stats,
          equity: equity,
          ohlcv: data.data.ohlcv,
          drawdown: data.data.drawdown,
          benchmark_drawdown: data.data.benchmark_drawdown,
          trades: trades,
          indicators: data.data.indicators || [],
          optimization: runMode === 'optimize'
            ? {
                mode: data.data.mode,
                heatmap: data.data.heatmap?.slice(0, 50),
                windows: data.data.windows,
                best_equity: bestEquity,
                oos_equity: data.data.oos_equity,
                benchmark_equity: data.data.benchmark_equity,
                stats: data.data.stats,
                equity: equity,
                ohlcv: data.data.ohlcv,
                indicators: data.data.indicators || [],
                trades: trades,
              }
            : null,
          output: data.data.output,
        };
        try {
          localStorage.setItem('lastRunData', JSON.stringify(runData));
        } catch (e) {
          console.warn('Failed to save to localStorage:', e);
          // Continue anyway - results will still be displayed
        }
        navigate('/quantgen/dashboard');
      }
    } catch (e: any) {
      setOutput(`Execution Error: ${e.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleSave = async () => {
    if (currentFilename) {
      await saveStrategy(currentFilename);
    } else {
      handleSaveAs();
    }
  };

  const handleSaveAs = async () => {
    const name = prompt('Enter strategy name:', '');
    if (!name) return;
    await saveStrategy(name);
  };

  const saveStrategy = async (name: string) => {
    try {
      const res = await fetch(`${API_URL}/strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, code }),
      });
      if (res.ok) {
        const safeName = name.endsWith('.py') ? name : `${name}.py`;
        setCurrentFilename(safeName);
        setOutput((prev) => prev + `\nSaved to ${safeName}`);
        loadStrategies();
      } else {
        const error = await res.text();
        alert(`Failed to save: ${error}`);
      }
    } catch (e: any) {
      alert(`Failed: ${e.message}`);
    }
  };

  const handleLoad = async (name: string) => {
    try {
      const res = await fetch(`${API_URL}/strategies/${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error('Failed to load');
      const data = await res.json();
      if (data.data?.code) {
        setCode(data.data.code);
        setCurrentFilename(name);
        setStrategyPrompt(`Loaded: ${name}`);
        setOutput(`Loaded ${name}`);
      }
    } catch {
      alert('Failed to load strategy');
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete ${name}?`)) return;
    try {
      const res = await fetch(`${API_URL}/strategies/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        loadStrategies();
      } else {
        alert('Failed to delete');
      }
    } catch {
      alert('Failed to delete');
    }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim() || isChatLoading) return;
    const userMessage = chatInput.trim();
    setChatInput('');
    setIsChatLoading(true);

    const newMessages: ChatMessage[] = [...chatMessages, { role: 'user', content: userMessage }];
    setChatMessages(newMessages);

    // If no code yet, suggest using the prompt box above
    if (!code) {
      setChatMessages([
        ...newMessages,
        { role: 'assistant', content: "I can help you build a strategy! Enter a description in the 'Strategy Description' box above and click 'Generate' to create code first. Then come back here to ask questions about it!" },
      ]);
      setIsChatLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, messages: newMessages }),
      });

      const data = await res.json();
      if (data.success && data.data?.response) {
        setChatMessages([
          ...newMessages,
          { role: 'assistant', content: data.data.response },
        ]);
      } else {
        setChatMessages([
          ...newMessages,
          { role: 'assistant', content: `Error: ${data.error?.message || 'Unknown error'}` },
        ]);
      }
    } catch (e: any) {
      setChatMessages([
        ...newMessages,
        { role: 'assistant', content: `Error: ${e.message}` },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col gap-4 p-6" style={{ backgroundColor: colors.surfaceAlt }}>
      {/* Input Area */}
      <div
        className="p-6 rounded-xl shadow-sm grid md:grid-cols-[1fr_auto] gap-6"
        style={{ backgroundColor: colors.surface, border: `1px solid ${colors.border}` }}
      >
        <div className="space-y-2">
          <label className="text-sm font-semibold uppercase tracking-wide" style={{ color: colors.muted }}>
            Strategy Description
          </label>
          <textarea
            value={strategyPrompt}
            onChange={(e) => setStrategyPrompt(e.target.value)}
            placeholder="Describe your strategy..."
            className="w-full h-24 border rounded-lg p-3 text-sm focus:border-emerald-500 focus:outline-none transition-all resize-none font-mono"
            style={{
              backgroundColor: colors.inputBg,
              borderColor: colors.border,
              color: colors.text
            }}
          />
        </div>

        <div className="flex flex-col justify-end gap-3 min-w-[180px]">
          <div className="space-y-2">
            <label className="text-sm font-semibold uppercase tracking-wide flex items-center gap-2" style={{ color: colors.muted }}>
              Tickers
              {fromScreenerTicker && (
                <span className="text-xs font-normal normal-case px-2 py-0.5 rounded-full" style={{
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                  color: '#10B981',
                  border: '1px solid rgba(16, 185, 129, 0.2)'
                }}>
                  From Screener
                </span>
              )}
            </label>
            <input
              type="text"
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="AAPL, MSFT"
              className="w-full border rounded-lg p-3 text-sm focus:border-emerald-500 focus:outline-none"
              style={{
                backgroundColor: colors.inputBg,
                borderColor: colors.border,
                color: colors.text
              }}
            />
          </div>

          <button
            onClick={handleGenerate}
            disabled={isGenerating || !strategyPrompt.trim()}
            className="w-full justify-center py-3 text-lg rounded-lg font-medium flex items-center gap-2 transition-colors text-white"
            style={{
              backgroundColor: isGenerating ? '#3F3F46' : '#10B981',
              opacity: isGenerating || !strategyPrompt.trim() ? 0.5 : 1,
              cursor: isGenerating || !strategyPrompt.trim() ? 'not-allowed' : 'pointer'
            }}
          >
            {isGenerating ? <Activity className="animate-spin" /> : <Sparkles />}
            Generate
          </button>
        </div>
      </div>

      {/* Workspace */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_350px] gap-4 min-h-0">
        {/* Left Column: Editor + Optimization Config */}
        <div className="flex flex-col gap-4 min-h-0 overflow-hidden">
          {/* Code Editor */}
          <div
            className="rounded-xl overflow-hidden shadow-sm flex flex-col flex-1 min-h-[400px]"
            style={{ backgroundColor: colors.surface, border: `1px solid ${colors.border}` }}
          >
            <div
              className="h-10 flex items-center px-4 justify-between"
              style={{ backgroundColor: isDarkMode ? 'rgba(0,0,0,0.3)' : '#f5f5f7', borderBottom: `1px solid ${colors.border}` }}
            >
              <span className="text-xs font-semibold uppercase flex items-center gap-2" style={{ color: colors.muted }}>
                <Terminal size={12} />
                {currentFilename ? (
                  <span className="text-emerald-500">{currentFilename}</span>
                ) : (
                  <span>Untitled</span>
                )}
              </span>
              {currentFilename && (
                <button
                  onClick={() => {
                    setCode('');
                    setCurrentFilename(null);
                    setStrategyPrompt('');
                    setOutput('');
                  }}
                  className="text-xs hover:text-emerald-500 transition-colors"
                  style={{ color: colors.muted }}
                >
                  New
                </button>
              )}
            </div>
            <div className="flex-1 relative">
              <Editor
                height="100%"
                defaultLanguage="python"
                theme={isDarkMode ? 'vs-dark' : 'vs'}
                value={code}
                onChange={(val) => setCode(val || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </div>

          {/* Optimization Config */}
          {runMode === 'optimize' && (
            <div
              className="rounded-xl overflow-hidden shadow-sm"
              style={{ backgroundColor: colors.surface, border: `1px solid ${colors.border}` }}
            >
              <OptimizationConfig
                config={optConfig}
                setConfig={setOptConfig}
                params={optParams}
                setParams={setOptParams}
              />
            </div>
          )}

          {/* Chat Assistant */}
          <div
            className="rounded-xl overflow-hidden shadow-sm flex flex-col max-h-[400px]"
            style={{ backgroundColor: colors.surface, border: `1px solid ${colors.border}` }}
          >
            <div
              className="h-10 flex items-center px-4 justify-between cursor-pointer"
              style={{ backgroundColor: isDarkMode ? 'rgba(0,0,0,0.3)' : '#f5f5f7', borderBottom: `1px solid ${colors.border}` }}
              onClick={() => setIsChatOpen(!isChatOpen)}
            >
              <span className="text-xs font-semibold uppercase flex items-center gap-2" style={{ color: colors.muted }}>
                <MessageCircle size={12} />
                AI Assistant
              </span>
              {isChatOpen ? (
                <ChevronDown size={14} style={{ color: colors.muted }} />
              ) : (
                <ChevronUp size={14} style={{ color: colors.muted }} />
              )}
            </div>

            {isChatOpen && (
              <div className="flex flex-col flex-1 min-h-[300px]">
                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {chatMessages.length === 0 ? (
                    <div className="text-xs text-center py-8 px-4" style={{ color: colors.muted }}>
                      <div className="mb-2">👋 Ask me anything about your strategy!</div>
                      <div style={{ opacity: 0.7 }}>
                        {code ? 'I can explain your code, suggest improvements, or help debug issues.' : 'Generate or load a strategy above, then come here to ask questions about it.'}
                      </div>
                    </div>
                  ) : (
                    chatMessages.map((msg, idx) => (
                      <div
                        key={idx}
                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className="max-w-[85%] rounded-lg p-2 text-xs"
                          style={{
                            backgroundColor: msg.role === 'user' ? colors.chatUserBg : colors.chatAssistantBg,
                            color: msg.role === 'user' ? '#ffffff' : colors.chatAssistantText
                          }}
                        >
                          {msg.content}
                        </div>
                      </div>
                    ))
                  )}
                  {isChatLoading && (
                    <div className="flex justify-start">
                      <div
                        className="rounded-lg p-2 text-xs animate-pulse"
                        style={{ backgroundColor: colors.chatAssistantBg, color: colors.muted }}
                      >
                        Thinking...
                      </div>
                    </div>
                  )}
                </div>

                {/* Input */}
                <div className="p-3" style={{ borderTop: `1px solid ${colors.border}` }}>
                  <div className="flex gap-2">
                    <textarea
                      ref={chatInputRef}
                      rows={6}
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendChat()}
                      placeholder={code ? 'Ask about your strategy...' : 'Type to ask questions...'}
                      disabled={isChatLoading}
                      className="flex-1 border rounded-md px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none resize-none"
                      style={{
                        backgroundColor: colors.inputBg,
                        borderColor: colors.border,
                        color: colors.text,
                        opacity: isChatLoading ? 0.5 : 1
                      }}
                    />
                    <button
                      onClick={handleSendChat}
                      disabled={!chatInput.trim() || isChatLoading}
                      className="p-2 rounded-md transition-colors text-white"
                      style={{
                        backgroundColor: isDarkMode ? '#10B981' : '#059669',
                        opacity: !chatInput.trim() || isChatLoading ? 0.5 : 1,
                        cursor: !chatInput.trim() || isChatLoading ? 'not-allowed' : 'pointer'
                      }}
                    >
                      <Send size={14} />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel */}
        <div className="flex flex-col gap-4 min-h-0">
          {/* Mode Toggle */}
          <div
            className="flex rounded-lg p-1"
            style={{ backgroundColor: isDarkMode ? 'rgba(0,0,0,0.3)' : '#f5f5f7', border: `1px solid ${colors.border}` }}
          >
            <button
              onClick={() => setRunMode('backtest')}
              className={`flex-1 text-xs py-2 rounded font-medium transition-all`}
              style={{
                backgroundColor: runMode === 'backtest' ? (isDarkMode ? '#27272A' : '#ffffff') : 'transparent',
                color: runMode === 'backtest' ? colors.text : colors.muted,
                boxShadow: runMode === 'backtest' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
              }}
            >
              Backtest
            </button>
            <button
              onClick={() => setRunMode('optimize')}
              className={`flex-1 text-xs py-2 rounded font-medium transition-all`}
              style={{
                backgroundColor: runMode === 'optimize' ? '#10B981' : 'transparent',
                color: runMode === 'optimize' ? '#ffffff' : colors.muted,
                boxShadow: runMode === 'optimize' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
              }}
            >
              Optimize
            </button>
          </div>

          {/* Run Button */}
          <button
            onClick={handleRun}
            disabled={isRunning || !code}
            className="w-full py-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors text-white"
            style={{
              backgroundColor: isDarkMode ? '#27272A' : '#1d1d1f',
              opacity: isRunning || !code ? 0.5 : 1,
              cursor: isRunning || !code ? 'not-allowed' : 'pointer'
            }}
            onMouseEnter={(e) => {
              if (!isRunning && code) {
                e.currentTarget.style.backgroundColor = isDarkMode ? '#3F3F46' : '#3f3f46';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = isDarkMode ? '#27272A' : '#1d1d1f';
            }}
          >
            {isRunning ? (
              <Activity className="animate-spin" size={16} />
            ) : runMode === 'optimize' ? (
              <Microscope size={16} />
            ) : (
              <Play size={16} />
            )}
            {runMode === 'optimize' ? 'Run Optimization' : 'Run Backtest'}
          </button>

          {/* Save Buttons */}
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={handleSave}
              disabled={!code}
              className="py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors"
              style={{
                backgroundColor: isDarkMode ? '#27272A' : '#f5f5f7',
                color: isDarkMode ? '#D4D4D8' : '#1d1d1f',
                opacity: !code ? 0.5 : 1,
                cursor: !code ? 'not-allowed' : 'pointer',
                border: `1px solid ${colors.border}`
              }}
              onMouseEnter={(e) => {
                if (code) {
                  e.currentTarget.style.backgroundColor = isDarkMode ? '#3F3F46' : '#e5e5e7';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = isDarkMode ? '#27272A' : '#f5f5f7';
              }}
            >
              <Save size={14} /> {currentFilename ? 'Save' : 'Save As'}
            </button>
            <button
              onClick={handleSaveAs}
              disabled={!code}
              className="py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors"
              style={{
                backgroundColor: isDarkMode ? '#27272A' : '#f5f5f7',
                color: isDarkMode ? '#D4D4D8' : '#1d1d1f',
                opacity: !code ? 0.5 : 1,
                cursor: !code ? 'not-allowed' : 'pointer',
                border: `1px solid ${colors.border}`
              }}
              onMouseEnter={(e) => {
                if (code) {
                  e.currentTarget.style.backgroundColor = isDarkMode ? '#3F3F46' : '#e5e5e7';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = isDarkMode ? '#27272A' : '#f5f5f7';
              }}
            >
              <FilePlus size={14} /> Save As
            </button>
          </div>

          {/* Saved Strategies */}
          <div
            className="rounded-xl overflow-hidden flex-1 flex flex-col min-h-[200px]"
            style={{ backgroundColor: colors.surface, border: `1px solid ${colors.border}` }}
          >
            <div
              className="p-3 font-semibold text-xs uppercase"
              style={{ backgroundColor: isDarkMode ? 'rgba(0,0,0,0.3)' : '#f5f5f7', color: colors.muted, borderBottom: `1px solid ${colors.border}` }}
            >
              Library ({strategies.length})
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {strategies.map((s) => (
                <div
                  key={s}
                  className="flex items-center justify-between p-2 rounded group cursor-pointer"
                  style={{
                    color: isDarkMode ? '#D4D4D8' : '#1d1d1f'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = isDarkMode ? 'rgba(63,63,70,0.5)' : '#e5e5e7';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <span onClick={() => handleLoad(s)} className="truncate flex-1">
                    {s}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(s);
                    }}
                    className="opacity-0 group-hover:opacity-100 transition-all p-1 rounded"
                    style={{ color: '#f43f5e' }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = 'rgba(244,63,94,0.1)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Console Output */}
          <div
            className="rounded-xl overflow-hidden flex-1 flex flex-col min-h-[200px] font-mono text-xs shadow-inner"
            style={{ backgroundColor: colors.consoleBg, border: `1px solid ${colors.border}` }}
          >
            <div
              className="p-2 flex justify-between items-center"
              style={{ backgroundColor: isDarkMode ? 'rgba(0,0,0,0.3)' : '#e5e5e7', borderBottom: `1px solid ${colors.border}` }}
            >
              <span style={{ color: colors.muted }}>Console Output</span>
              <div className="flex items-center gap-2">
                {isRunning && <span className="text-emerald-500 animate-pulse">Running...</span>}
                {output && (
                  <button
                    onClick={() => setOutput('')}
                    className="text-xs transition-colors"
                    style={{ color: colors.muted }}
                    onMouseEnter={(e) => e.currentTarget.style.color = colors.text}
                    onMouseLeave={(e) => e.currentTarget.style.color = colors.muted}
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>
            <div className="p-3 overflow-auto whitespace-pre-wrap flex-1" style={{ color: colors.consoleText }}>
              {output || <span style={{ opacity: 0.3 }}>Waiting for execution...</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
