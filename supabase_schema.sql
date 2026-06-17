-- Enable uuid generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- LAYER 3: IDENTITY RESOLUTION (Base Entities)
-- ==========================================
CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255),
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE identities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES persons(id),
    source VARCHAR(50) NOT NULL,      -- stripe, whatsapp, trainerize
    external_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, external_id)
);
CREATE INDEX idx_identities_person ON identities(person_id);

CREATE TABLE coaches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES persons(id),
    business_tier VARCHAR(50)
);

CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES persons(id),
    coach_id UUID NOT NULL REFERENCES coaches(id),
    status VARCHAR(50) DEFAULT 'active'
);

CREATE TABLE programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID NOT NULL REFERENCES coaches(id),
    name VARCHAR(255) NOT NULL
);

-- Secure Webhook endpoint token table (removes guessable coach UUID in URL)
CREATE TABLE webhook_endpoints (
    webhook_token UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID NOT NULL REFERENCES coaches(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- LAYER 1 & 2: INGESTION
-- ==========================================
CREATE TABLE raw_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_raw_events_source_ext ON raw_events(source, external_id);

CREATE TABLE canonical_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    event_domain VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    structured_payload JSONB,
    raw_event_id UUID REFERENCES raw_events(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_canonical_events_entity ON canonical_events(entity_type, entity_id);

-- ==========================================
-- LAYER 4 & 5: STATE & TIMELINE
-- ==========================================
CREATE TABLE entity_state (
    entity_id UUID PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    engagement_score INTEGER DEFAULT 100,
    compliance_score INTEGER DEFAULT 100,
    revenue_health INTEGER DEFAULT 100,
    churn_probability FLOAT DEFAULT 0.0,
    last_checkin TIMESTAMPTZ,
    last_payment TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE entity_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    date DATE NOT NULL,
    state JSONB NOT NULL,
    UNIQUE(entity_id, date)
);
CREATE INDEX idx_entity_snapshots_entity_date ON entity_snapshots(entity_id, date DESC);

-- ==========================================
-- LAYER 6: FEATURE STORE
-- ==========================================
CREATE TABLE feature_store (
    entity_id UUID PRIMARY KEY,
    days_since_checkin INTEGER,
    days_since_payment INTEGER,
    message_response_time_avg FLOAT,
    workout_completion_rate FLOAT,
    weekly_weight_change FLOAT,
    coach_response_time_avg FLOAT,
    payment_retry_count INTEGER,
    program_adherence_rate FLOAT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- LAYER 8: SIGNALS
-- ==========================================
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID REFERENCES coaches(id),
    entity_id UUID NOT NULL,
    signal_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    confidence FLOAT NOT NULL,
    evidence JSONB,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_signals_entity_type ON signals(entity_id, signal_type);

-- ==========================================
-- LAYER 7 & 9: PREDICTIONS
-- ==========================================
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    prediction_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_id, model_name)
);
CREATE INDEX idx_predictions_entity_created ON predictions(entity_id, created_at DESC);

-- ==========================================
-- LAYER 10: ACTION GRAPH
-- ==========================================
CREATE TABLE actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    coach_id UUID REFERENCES coaches(id),
    priority INTEGER NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    reason JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'suggested',
    actioned_by UUID,
    actioned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- ==========================================

-- Enable RLS on core data tables
ALTER TABLE persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaches ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_store ENABLE ROW LEVEL SECURITY;

-- 1. Coaches Policy: Coach can only query/view their own record
CREATE POLICY coach_self_policy ON coaches 
    FOR ALL USING (person_id = auth.uid());

-- 2. Clients Policy: Coach can select/insert clients mapped to their coach ID
CREATE POLICY client_scope_policy ON clients
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE person_id = auth.uid())
    );

-- 3. Webhook Endpoints Policy: Only authenticated coaches can configure endpoints
CREATE POLICY webhook_endpoints_policy ON webhook_endpoints
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE person_id = auth.uid())
    );

-- 4. Signals Policy: Scoped strictly to Coach who owns the relation
CREATE POLICY signals_coach_policy ON signals
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE person_id = auth.uid())
    );

-- 5. Actions Policy: Scoped to the Coach
CREATE POLICY actions_coach_policy ON actions
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE person_id = auth.uid())
    );

-- 6. Entity State & Feature Store select permissions through clients association
CREATE POLICY entity_state_scope_policy ON entity_state
    FOR SELECT USING (
        entity_id IN (
            SELECT person_id FROM clients WHERE coach_id IN (
                SELECT id FROM coaches WHERE person_id = auth.uid()
            )
        )
    );

CREATE POLICY feature_store_scope_policy ON feature_store
    FOR SELECT USING (
        entity_id IN (
            SELECT person_id FROM clients WHERE coach_id IN (
                SELECT id FROM coaches WHERE person_id = auth.uid()
            )
        )
    );
