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
    auth_user_id UUID UNIQUE,
    business_tier VARCHAR(50),
    stripe_connected_account_id VARCHAR(255)
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

-- enrollments table to link clients to programs
CREATE TABLE enrollments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    coach_id UUID NOT NULL REFERENCES coaches(id),
    status VARCHAR(50) DEFAULT 'active', -- active, completed, cancelled
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_enrollments_coach ON enrollments(coach_id);
CREATE INDEX idx_enrollments_client ON enrollments(client_id);

-- program_sessions table to track workouts and calendar compliance
CREATE TABLE program_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    enrollment_id UUID NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    coach_id UUID NOT NULL REFERENCES coaches(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    session_date DATE NOT NULL,
    status VARCHAR(50) DEFAULT 'scheduled', -- scheduled, completed, missed
    feedback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_program_sessions_coach ON program_sessions(coach_id);
CREATE INDEX idx_program_sessions_client ON program_sessions(client_id);

-- Secure Webhook endpoint token table with per-coach Stripe webhook secrets
CREATE TABLE webhook_endpoints (
    webhook_token UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID NOT NULL REFERENCES coaches(id),
    stripe_webhook_secret VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- LAYER 1 & 2: INGESTION (With coach_id Denormalization)
-- ==========================================
CREATE TABLE raw_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID REFERENCES coaches(id), -- Denormalized for tenant safety
    source VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_raw_events_source_ext ON raw_events(source, external_id);
CREATE INDEX idx_raw_events_coach ON raw_events(coach_id);

CREATE TABLE canonical_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID REFERENCES coaches(id), -- Denormalized for tenant safety
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
CREATE INDEX idx_canonical_events_coach ON canonical_events(coach_id);

-- ==========================================
-- LAYER 4 & 5: STATE & TIMELINE (With coach_id Denormalization)
-- ==========================================
CREATE TABLE entity_state (
    entity_id UUID PRIMARY KEY,
    coach_id UUID REFERENCES coaches(id), -- Denormalized for tenant safety
    entity_type VARCHAR(50) NOT NULL,
    engagement_score INTEGER DEFAULT 100,
    compliance_score INTEGER DEFAULT 100,
    revenue_health INTEGER DEFAULT 100,
    churn_probability FLOAT DEFAULT 0.0,
    last_checkin TIMESTAMPTZ,
    last_payment TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_entity_state_coach ON entity_state(coach_id);

CREATE TABLE entity_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    coach_id UUID REFERENCES coaches(id), -- Denormalized for tenant safety
    date DATE NOT NULL,
    state JSONB NOT NULL,
    UNIQUE(entity_id, date)
);
CREATE INDEX idx_entity_snapshots_entity_date ON entity_snapshots(entity_id, date DESC);
CREATE INDEX idx_entity_snapshots_coach ON entity_snapshots(coach_id);

-- ==========================================
-- LAYER 6: FEATURE STORE (With coach_id Denormalization; Static Deltas Dropped)
-- ==========================================
CREATE TABLE feature_store (
    entity_id UUID PRIMARY KEY,
    coach_id UUID REFERENCES coaches(id), -- Denormalized for tenant safety
    message_response_time_avg FLOAT,
    workout_completion_rate FLOAT,
    weekly_weight_change FLOAT,
    last_known_weight FLOAT,
    last_failed_payment_amount FLOAT DEFAULT 0.0,
    coach_response_time_avg FLOAT,
    payment_retry_count INTEGER,
    program_adherence_rate FLOAT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_feature_store_coach ON feature_store(coach_id);

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
CREATE INDEX idx_signals_coach ON signals(coach_id);

-- ==========================================
-- LAYER 7 & 9: PREDICTIONS (With coach_id Denormalization)
-- ==========================================
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    coach_id UUID REFERENCES coaches(id), -- Denormalized for tenant safety
    model_name VARCHAR(100) NOT NULL,
    prediction_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_id, model_name)
);
CREATE INDEX idx_predictions_entity_created ON predictions(entity_id, created_at DESC);
CREATE INDEX idx_predictions_coach ON predictions(coach_id);

-- ==========================================
-- LAYER 10: ACTION GRAPH
-- ==========================================
CREATE TABLE actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    coach_id UUID REFERENCES coaches(id),
    signal_id UUID REFERENCES signals(id),
    priority INTEGER NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    reason JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'suggested',
    actioned_by UUID,
    actioned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_actions_coach ON actions(coach_id);

-- briefings table to cache daily briefings with a TTL check
CREATE TABLE briefings (
    coach_id UUID PRIMARY KEY REFERENCES coaches(id),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    briefing_content JSONB NOT NULL
);

-- ==========================================
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- ==========================================
ALTER TABLE persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaches ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE programs ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE program_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_store ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefings ENABLE ROW LEVEL SECURITY;

-- Decoupled RLS Policies using denormalized coach_id lookup (maximum query optimization)
CREATE POLICY persons_coach_policy ON persons
    FOR ALL USING (
        id IN (
            SELECT person_id FROM clients WHERE coach_id IN (
                SELECT id FROM coaches WHERE auth_user_id = auth.uid()
            )
        ) OR id IN (
            SELECT person_id FROM coaches WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY identities_coach_policy ON identities
    FOR ALL USING (
        person_id IN (
            SELECT person_id FROM clients WHERE coach_id IN (
                SELECT id FROM coaches WHERE auth_user_id = auth.uid()
            )
        ) OR person_id IN (
            SELECT person_id FROM coaches WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY coach_self_policy ON coaches 
    FOR ALL USING (auth_user_id = auth.uid());

CREATE POLICY client_scope_policy ON clients
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY programs_coach_policy ON programs
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY enrollments_coach_policy ON enrollments
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY program_sessions_coach_policy ON program_sessions
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY webhook_endpoints_policy ON webhook_endpoints
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY raw_events_coach_policy ON raw_events
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY canonical_events_coach_policy ON canonical_events
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY entity_state_scope_policy ON entity_state
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY entity_snapshots_coach_policy ON entity_snapshots
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY feature_store_scope_policy ON feature_store
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY signals_coach_policy ON signals
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY predictions_coach_policy ON predictions
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY actions_coach_policy ON actions
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

CREATE POLICY briefings_coach_policy ON briefings
    FOR ALL USING (
        coach_id IN (SELECT id FROM coaches WHERE auth_user_id = auth.uid())
    );

-- ==========================================
-- DATABASE ATOMIC MUTATION PL/PGSQL FUNCTIONS
-- ==========================================
CREATE OR REPLACE FUNCTION mutate_entity_state(
    p_entity_id UUID,
    p_coach_id UUID, -- Denormalized parameter to enforce structural tenant safety
    p_entity_type VARCHAR,
    p_engagement_delta INT,
    p_compliance_delta INT,
    p_revenue_delta INT,
    p_engagement_override INT DEFAULT NULL,
    p_compliance_override INT DEFAULT NULL,
    p_revenue_override INT DEFAULT NULL,
    p_last_checkin TIMESTAMPTZ DEFAULT NULL,
    p_last_payment TIMESTAMPTZ DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO entity_state (
        entity_id, 
        coach_id,
        entity_type, 
        engagement_score, 
        compliance_score, 
        revenue_health, 
        last_checkin, 
        last_payment
    ) VALUES (
        p_entity_id, 
        p_coach_id,
        p_entity_type, 
        COALESCE(p_engagement_override, 100), 
        COALESCE(p_compliance_override, 100), 
        COALESCE(p_revenue_override, 100), 
        p_last_checkin, 
        p_last_payment
    ) ON CONFLICT (entity_id) DO UPDATE SET
        coach_id = COALESCE(p_coach_id, entity_state.coach_id),
        engagement_score = CASE 
            WHEN p_engagement_override IS NOT NULL THEN p_engagement_override
            ELSE GREATEST(0, LEAST(100, entity_state.engagement_score + COALESCE(p_engagement_delta, 0)))
        END,
        compliance_score = CASE 
            WHEN p_compliance_override IS NOT NULL THEN p_compliance_override
            ELSE GREATEST(0, LEAST(100, entity_state.compliance_score + COALESCE(p_compliance_delta, 0)))
        END,
        revenue_health = CASE 
            WHEN p_revenue_override IS NOT NULL THEN p_revenue_override
            ELSE GREATEST(0, LEAST(100, entity_state.revenue_health + COALESCE(p_revenue_delta, 0)))
        END,
        last_checkin = COALESCE(p_last_checkin, entity_state.last_checkin),
        last_payment = COALESCE(p_last_payment, entity_state.last_payment),
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;
