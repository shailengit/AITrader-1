-- Create earnings_calendar table for TradeCraft
-- Run this against the sp1500_1d database

CREATE TABLE IF NOT EXISTS earnings_calendar (
    ticker VARCHAR(10) NOT NULL,
    report_date DATE NOT NULL,
    fiscal_year INT,
    fiscal_quarter INT,
    eps_estimate NUMERIC(12, 4),
    revenue_estimate NUMERIC(20, 2),
    eps_actual NUMERIC(12, 4),
    revenue_actual NUMERIC(20, 2),
    time_of_day VARCHAR(10) DEFAULT 'tns',
    source VARCHAR(20) DEFAULT 'finnhub',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, report_date)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_earnings_report_date ON earnings_calendar(report_date);
CREATE INDEX IF NOT EXISTS idx_earnings_ticker ON earnings_calendar(ticker);

-- Trigger to auto-update updated_at on modification
CREATE OR REPLACE FUNCTION update_earnings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_earnings_updated_at ON earnings_calendar;
CREATE TRIGGER trg_earnings_updated_at
    BEFORE UPDATE ON earnings_calendar
    FOR EACH ROW
    EXECUTE FUNCTION update_earnings_updated_at();
