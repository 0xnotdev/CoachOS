-- Enable the pgvector extension to work with embeddings
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create the canonical events table
CREATE TABLE IF NOT EXISTS canonical_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    coach_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    event_domain VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    source VARCHAR(50) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL,
    metadata JSONB NOT NULL,
    -- Embedding column for similarity matching of event semantic meanings
    embedding VECTOR(768) 
);

-- Indexes for frequent queries and filtering
CREATE INDEX idx_events_coach_id ON canonical_events(coach_id);
CREATE INDEX idx_events_entity ON canonical_events(entity_type, entity_id);
CREATE INDEX idx_events_domain_type ON canonical_events(event_domain, event_type);
CREATE INDEX idx_events_payload_gin ON canonical_events USING GIN (payload);

-- HNSW Index for fast vector similarity search
CREATE INDEX idx_events_embedding ON canonical_events USING hnsw (embedding vector_l2_ops);

-- Row Level Security (RLS)
ALTER TABLE canonical_events ENABLE ROW LEVEL SECURITY;

-- Coaches can only see their own events
CREATE POLICY "Coaches can access their own data" 
ON canonical_events 
FOR ALL 
USING (auth.uid() = coach_id);
