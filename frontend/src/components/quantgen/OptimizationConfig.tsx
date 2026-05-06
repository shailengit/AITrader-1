import { useState } from "react";
import { Settings, Plus, Trash2, Microscope } from "lucide-react";

interface ParamRange {
  name: string;
  start: number;
  stop: number;
  step: number;
}

interface WFOConfig {
  type: "rolling" | "expanding";
  windows: number;
  ratio: number;
  splitMethod: "ratio" | "fixed";
  train_days: number;
  test_days: number;
  start_date: string;
  end_date: string;
}

interface OptimizationConfigData {
  mode: "simple" | "wfo" | "true_wfo";
  metric: "total_return" | "sharpe" | "sortino" | "max_dd";
  wfo: WFOConfig;
}

interface OptimizationConfigProps {
  config: OptimizationConfigData;
  setConfig: (config: OptimizationConfigData) => void;
  params: ParamRange[];
  setParams: (params: ParamRange[]) => void;
}

export default function OptimizationConfig({
  config,
  setConfig,
  params,
  setParams,
}: OptimizationConfigProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "9px 12px",
    borderRadius: "8px",
    border: "1px solid var(--border)",
    backgroundColor: "var(--canvas)",
    color: "var(--foreground)",
    fontSize: "14px",
    outline: "none",
  };

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: "pointer",
  };

  const addParam = () =>
    setParams([...params, { name: "", start: 10, stop: 50, step: 10 }]);
  const removeParam = (index: number) =>
    setParams(params.filter((_, i) => i !== index));
  const updateParam = (index: number, field: keyof ParamRange, value: any) => {
    const newParams = [...params];
    newParams[index] = { ...newParams[index], [field]: value };
    setParams(newParams);
  };

  return (
    <div>
      <button
        style={{
          height: "44px",
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 16px",
          backgroundColor: "var(--surface-raised)",
          border: "none",
          borderBottom: "1px solid var(--border)",
          cursor: "pointer",
          color: "var(--foreground)",
        }}
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-label="Toggle optimization config"
      >
        <span
          style={{
            fontSize: "12px",
            fontWeight: 600,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            color: "var(--subtle)",
          }}
        >
          <Microscope size={14} />
          Optimization Config
        </span>
        <span style={{ fontSize: "12px", color: "var(--subtle)" }}>
          {isExpanded ? "▼" : "▶"}
        </span>
      </button>

      {isExpanded && (
        <div style={{ padding: "16px" }}>
          {/* Mode & Metric */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "8px",
              marginBottom: "12px",
            }}
          >
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--subtle)",
                  marginBottom: "8px",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                }}
              >
                Mode
              </label>
              <select
                value={config.mode}
                onChange={(e) =>
                  setConfig({ ...config, mode: e.target.value as any })
                }
                style={selectStyle}
              >
                <option value="simple">Simple (Grid Search)</option>
                <option value="wfo">Walk-Forward</option>
                <option value="true_wfo">True Walk-Forward</option>
              </select>
              {config.mode === "true_wfo" && (
                <p
                  style={{
                    fontSize: "13px",
                    color: "var(--accent)",
                    marginTop: "6px",
                    lineHeight: 1.5,
                  }}
                >
                  Optimizes on training window, trades single next day,
                  maintains positions across windows.
                </p>
              )}
            </div>
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--subtle)",
                  marginBottom: "8px",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                }}
              >
                Metric
              </label>
              <select
                value={config.metric}
                onChange={(e) =>
                  setConfig({ ...config, metric: e.target.value as any })
                }
                style={selectStyle}
              >
                <option value="total_return">Total Return</option>
                <option value="sharpe">Sharpe Ratio</option>
                <option value="sortino">Sortino Ratio</option>
                <option value="max_dd">Max Drawdown</option>
              </select>
            </div>
          </div>

          {/* Date Range */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "8px",
              marginBottom: "12px",
              paddingBottom: "12px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--subtle)",
                  marginBottom: "8px",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                }}
              >
                Start Date
              </label>
              <input
                type="date"
                value={config.wfo.start_date}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    wfo: { ...config.wfo, start_date: e.target.value },
                  })
                }
                style={inputStyle}
              />
            </div>
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--subtle)",
                  marginBottom: "8px",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                }}
              >
                End Date
              </label>
              <input
                type="date"
                value={config.wfo.end_date}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    wfo: { ...config.wfo, end_date: e.target.value },
                  })
                }
                style={inputStyle}
              />
            </div>
          </div>

          {/* Parameters */}
          <div style={{ marginBottom: "12px" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "8px",
              }}
            >
              <label
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--subtle)",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <Settings size={13} /> Parameters
              </label>
              <button
                onClick={addParam}
                style={{
                  fontSize: "12px",
                  color: "var(--accent)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  fontWeight: 600,
                  padding: "6px 10px",
                  borderRadius: "6px",
                }}
              >
                <Plus size={12} /> Add
              </button>
            </div>
            {params.length === 0 && (
              <p
                style={{
                  fontSize: "14px",
                  color: "var(--muted)",
                  fontStyle: "italic",
                  lineHeight: 1.5,
                }}
              >
                No parameters configured. Define parameters in your strategy
                code (e.g.,{" "}
                <code style={{ fontSize: "inherit", color: "var(--accent)" }}>
                  sma_window = 20
                </code>
                ), then they will appear here.
              </p>
            )}
            {params.map((param, index) => (
              <div
                key={index}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr 1fr 24px",
                  gap: "4px",
                  alignItems: "center",
                  marginBottom: "4px",
                  padding: "6px",
                  borderRadius: "8px",
                  backgroundColor: "var(--canvas)",
                }}
              >
                <input
                  type="text"
                  value={param.name}
                  onChange={(e) => updateParam(index, "name", e.target.value)}
                  placeholder="name"
                  style={inputStyle}
                />
                <input
                  type="number"
                  value={param.start}
                  onChange={(e) =>
                    updateParam(index, "start", parseFloat(e.target.value))
                  }
                  placeholder="Start"
                  style={inputStyle}
                />
                <input
                  type="number"
                  value={param.stop}
                  onChange={(e) =>
                    updateParam(index, "stop", parseFloat(e.target.value))
                  }
                  placeholder="Stop"
                  style={inputStyle}
                />
                <input
                  type="number"
                  value={param.step}
                  onChange={(e) =>
                    updateParam(index, "step", parseFloat(e.target.value))
                  }
                  placeholder="Step"
                  style={inputStyle}
                />
                <button
                  onClick={() => removeParam(index)}
                  aria-label={`Remove parameter ${param.name || index + 1}`}
                  style={{
                    padding: "6px",
                    borderRadius: "6px",
                    border: "none",
                    background: "none",
                    color: "var(--danger)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    minWidth: "32px",
                    minHeight: "32px",
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>

          {/* WFO Settings */}
          {(config.mode === "wfo" || config.mode === "true_wfo") && (
            <div
              style={{
                paddingTop: "10px",
                borderTop: "1px solid var(--border)",
              }}
            >
              <label
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--subtle)",
                  marginBottom: "10px",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                }}
              >
                Walk-Forward Settings
              </label>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "8px",
                }}
              >
                <div>
                  <label
                    style={{
                      display: "block",
                      fontSize: "12px",
                      color: "var(--subtle)",
                      marginBottom: "6px",
                    }}
                  >
                    Window Type
                  </label>
                  <select
                    value={config.wfo.type}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        wfo: { ...config.wfo, type: e.target.value as any },
                      })
                    }
                    style={selectStyle}
                  >
                    <option value="rolling">Rolling</option>
                    <option value="expanding">Expanding</option>
                  </select>
                </div>
                <div>
                  <label
                    style={{
                      display: "block",
                      fontSize: "12px",
                      color: "var(--subtle)",
                      marginBottom: "6px",
                    }}
                  >
                    Split Method
                  </label>
                  <select
                    value={config.wfo.splitMethod}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        wfo: {
                          ...config.wfo,
                          splitMethod: e.target.value as any,
                        },
                      })
                    }
                    style={selectStyle}
                  >
                    <option value="ratio">Ratio</option>
                    <option value="fixed">Fixed Days</option>
                  </select>
                </div>
                {config.wfo.splitMethod === "fixed" ? (
                  <>
                    <div>
                      <label
                        style={{
                          display: "block",
                          fontSize: "18px",
                          color: "var(--muted)",
                          marginBottom: "5px",
                        }}
                      >
                        Train Days
                      </label>
                      <input
                        type="number"
                        min="14"
                        value={config.wfo.train_days}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            wfo: {
                              ...config.wfo,
                              train_days: parseInt(e.target.value),
                            },
                          })
                        }
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          display: "block",
                          fontSize: "18px",
                          color: "var(--muted)",
                          marginBottom: "5px",
                        }}
                      >
                        Test Days
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={config.wfo.test_days}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            wfo: {
                              ...config.wfo,
                              test_days: parseInt(e.target.value),
                            },
                          })
                        }
                        style={inputStyle}
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <label
                        style={{
                          display: "block",
                          fontSize: "18px",
                          color: "var(--muted)",
                          marginBottom: "5px",
                        }}
                      >
                        Train/Test Ratio
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        min="0.1"
                        max="0.9"
                        value={config.wfo.ratio}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            wfo: {
                              ...config.wfo,
                              ratio: parseFloat(e.target.value),
                            },
                          })
                        }
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          display: "block",
                          fontSize: "18px",
                          color: "var(--muted)",
                          marginBottom: "5px",
                        }}
                      >
                        Windows
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={config.wfo.windows}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            wfo: {
                              ...config.wfo,
                              windows: parseInt(e.target.value),
                            },
                          })
                        }
                        style={inputStyle}
                      />
                    </div>
                  </>
                )}
              </div>
              {config.wfo.splitMethod === "fixed" &&
                config.wfo.test_days === 1 && (
                  <p
                    style={{
                      fontSize: "13px",
                      color: "var(--accent)",
                      marginTop: "8px",
                      lineHeight: 1.5,
                    }}
                  >
                    Single-day testing: each window tests 1 day and advances by
                    1 day. Creates maximum windows.
                  </p>
                )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
