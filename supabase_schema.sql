-- Enable uuid generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- LAYER 1: EVENT INGESTION
-- ==========================================
CREATE TABLE raw_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL, -- stripe, trainerize, whatsapp, typeform
    external_id VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_raw_events_source_ext ON raw_events(source, external_id);

-- ==========================================
-- LAYER 2: CANONICAL EVENT SYSTEM
-- ==========================================
CREATE TABLE canonical_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL, -- client, coach, lead
    entity_id UUID NOT NULL,          -- maps to clients.id, etc.
    event_domain VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL, -- payment_failed, workout_missed, message_received
    timestamp TIMESTAMPTZ NOT NULL,
    raw_event_id UUID REFERENCES raw_events(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_canonical_events_entity ON canonical_events(entity_type, entity_id);

-- ==========================================
-- LAYER 3: IDENTITY RESOLUTION
-- ==========================================
CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255),
    email VARCHAR(255),
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

-- DOMAIN ENTITIES
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

-- ==========================================
-- LAYER 4 & 5: ENTITY STATE & TEMPORAL INTELLIGENCE
-- ==========================================
CREATE TABLE entity_state (
    entity_id UUID PRIMARY KEY, -- client_id, coach_id, etc.
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
    state JSONB NOT NULL, -- Snapshot of engagement, compliance, weight, etc.
    UNIQUE(entity_id, date)
);

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
-- LAYER 8: SIGNAL DETECTION ENGINE
-- ==========================================
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID REFERENCES coaches(id),
    entity_id UUID NOT NULL,
    signal_type VARCHAR(100) NOT NULL, -- engagement_collapse, transformation_stall
    severity VARCHAR(20) NOT NULL,     -- low, medium, high, critical
    confidence FLOAT NOT NULL,
    evidence JSONB,                    -- Array of canonical_event IDs or feature values
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- LAYER 7 & 9: PREDICTIONS & DECISIONS
-- ==========================================
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    model_name VARCHAR(100) NOT NULL,  -- churn_model, expansion_model
    prediction_value JSONB NOT NULL,   -- e.g., {"probability": 0.84}
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- LAYER 10: ACTION GRAPH
-- ==========================================
CREATE TABLE actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,           -- Who this action is for
    coach_id UUID REFERENCES coaches(id),
    priority INTEGER NOT NULL,         -- 0-100
    action_type VARCHAR(100) NOT NULL, -- schedule_intervention, offer_upsell
    reason JSONB NOT NULL,             -- Underlying signal or prediction
    status VARCHAR(50) DEFAULT 'suggested', -- suggested, accepted, rejected, completed
    actioned_by UUID,                  -- Coach or Agent that executed/dismissed the action
    actioned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
