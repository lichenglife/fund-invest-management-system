CREATE TABLE funds (
    code VARCHAR(12) NOT NULL,
    name VARCHAR(64) NOT NULL,
    type VARCHAR(16) NOT NULL,
    sub_type VARCHAR(32),
    theme VARCHAR(32),
    style VARCHAR(16),
    launch_date DATE,
    source VARCHAR(32) NOT NULL,
    as_of DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (code)
);
CREATE INDEX ix_funds_type_theme ON funds (type, theme);
CREATE TABLE paper_accounts (
    account_id VARCHAR(32) NOT NULL,
    init_capital NUMERIC(18, 2) DEFAULT 1000000 NOT NULL,
    cash NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (account_id)
);
CREATE TABLE holdings (
    code VARCHAR(12) NOT NULL,
    report_date DATE NOT NULL,
    stock_code VARCHAR(12) NOT NULL,
    stock_name VARCHAR(64),
    weight NUMERIC(12, 6),
    source VARCHAR(32) NOT NULL,
    as_of DATE NOT NULL,
    PRIMARY KEY (code, report_date, stock_code),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
CREATE TABLE navs (
    code VARCHAR(12) NOT NULL,
    trade_date DATE NOT NULL,
    nav NUMERIC(18, 4) NOT NULL,
    acc_nav NUMERIC(18, 4),
    adj_nav NUMERIC(18, 4) NOT NULL,
    is_estimate BOOLEAN DEFAULT false NOT NULL,
    source VARCHAR(32) NOT NULL,
    as_of DATE NOT NULL,
    PRIMARY KEY (code, trade_date),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
CREATE INDEX ix_navs_date ON navs (trade_date);
CREATE TABLE paper_positions (
    account_id VARCHAR(32) NOT NULL,
    code VARCHAR(12) NOT NULL,
    shares NUMERIC(18, 4) NOT NULL,
    cost NUMERIC(18, 4) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (account_id, code),
    FOREIGN KEY(account_id) REFERENCES paper_accounts (account_id) ON DELETE CASCADE,
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
CREATE TABLE paper_trades (
    trade_id BIGSERIAL NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    code VARCHAR(12) NOT NULL,
    side VARCHAR(4) NOT NULL,
    shares NUMERIC(18, 4) NOT NULL,
    nav NUMERIC(18, 4) NOT NULL,
    trade_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (trade_id),
    CONSTRAINT ck_paper_trades_side CHECK (side IN ('buy','sell')),
    FOREIGN KEY(account_id) REFERENCES paper_accounts (account_id) ON DELETE CASCADE,
    FOREIGN KEY(code) REFERENCES funds (code)
);
CREATE INDEX ix_trades_account ON paper_trades (account_id, trade_date);
CREATE TABLE portfolios (
    portfolio_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    name VARCHAR(64),
    source VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (portfolio_id),
    CONSTRAINT ck_portfolios_source CHECK (source IN ('template','manual','import')),
    FOREIGN KEY(account_id) REFERENCES paper_accounts (account_id) ON DELETE CASCADE
);
CREATE TABLE research_metrics (
    code VARCHAR(12) NOT NULL,
    alpha NUMERIC(12, 6),
    beta NUMERIC(12, 6),
    tracking_error NUMERIC(12, 6),
    info_ratio NUMERIC(12, 6),
    peg NUMERIC(12, 6),
    erp NUMERIC(12, 6),
    peg_available BOOLEAN DEFAULT false NOT NULL,
    erp_available BOOLEAN DEFAULT false NOT NULL,
    cv_flag BOOLEAN DEFAULT false NOT NULL,
    as_of DATE NOT NULL,
    PRIMARY KEY (code),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
CREATE TABLE scores (
    code VARCHAR(12) NOT NULL,
    "window" VARCHAR(8) DEFAULT '3y' NOT NULL,
    weights JSONB NOT NULL,
    composite NUMERIC(8, 4) NOT NULL,
    factors JSONB NOT NULL,
    as_of DATE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (code),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
CREATE TABLE portfolio_weights (
    portfolio_id VARCHAR(32) NOT NULL,
    code VARCHAR(12) NOT NULL,
    weight NUMERIC(8, 4) NOT NULL,
    PRIMARY KEY (portfolio_id, code),
    FOREIGN KEY(code) REFERENCES funds (code),
    FOREIGN KEY(portfolio_id) REFERENCES portfolios (portfolio_id) ON DELETE CASCADE
);
CREATE TABLE admin_users (
    id BIGSERIAL NOT NULL,
    username VARCHAR(64) NOT NULL,
    password_encrypted VARCHAR(256) NOT NULL,
    must_change_password BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (username)
);
CREATE TABLE data_quality_log (
    id BIGSERIAL NOT NULL,
    entity VARCHAR(32),
    check_date DATE,
    missing_count INTEGER,
    anomaly_flag BOOLEAN,
    cv_error NUMERIC(8, 4),
    source VARCHAR(32),
    as_of DATE,
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE fund_dividends (
    code VARCHAR(12) NOT NULL,
    ex_date DATE NOT NULL,
    div_per_unit NUMERIC(10, 6),
    source VARCHAR(32),
    PRIMARY KEY (code, ex_date)
);
CREATE TABLE scheduler_jobs (
    id BIGSERIAL NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    job_name VARCHAR(128),
    trigger VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    error TEXT,
    args JSONB,
    result_summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);
CREATE INDEX ix_scheduler_jobs_job_id ON scheduler_jobs (job_id);
CREATE INDEX ix_scheduler_jobs_status ON scheduler_jobs (status);
