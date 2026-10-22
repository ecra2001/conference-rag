"""
Step 1: Create Database Schema
================================
Creates the sentence_embeddings table, pgvector extension,
Row Level Security policies, and the match_sentences() function
in your Supabase database.

Usage:
    python scripts/01_create_schema.py

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key, access token, and project ref
    - Supabase project created
"""

import json
import sys
import time

# Load configuration from both config files
with open('config.public.json', 'r') as f:
    public_config = json.load(f)
with open('config.secret.json', 'r') as f:
    secrets = json.load(f)

SUPABASE_URL = public_config['SUPABASE_URL']
SUPABASE_SERVICE_KEY = secrets['SUPABASE_SERVICE_KEY']
SUPABASE_ACCESS_TOKEN = secrets['SUPABASE_ACCESS_TOKEN']
SUPABASE_PROJECT_REF = secrets['SUPABASE_PROJECT_REF']


def create_schema():
    import requests
    from supabase import create_client

    print("=" * 60)
    print("Creating Database Schema")
    print("=" * 60)

    schema_sql = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create sentence_embeddings table
CREATE TABLE IF NOT EXISTS sentence_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talk_id UUID NOT NULL,
    title TEXT NOT NULL,
    speaker TEXT,
    calling TEXT,
    year INTEGER,
    season TEXT,
    url TEXT,
    sentence_num INTEGER,
    text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for talk_id grouping
CREATE INDEX IF NOT EXISTS sentence_embeddings_talk_id_idx 
ON sentence_embeddings(talk_id);

-- Keep vector search fast over the full imported corpus and speaker filtering fast
-- when a speaker is selected. The normalized-speaker expression matches the
-- normalization used by match_sentences() and get_speakers().
CREATE INDEX IF NOT EXISTS sentence_embeddings_embedding_ivfflat_idx
ON sentence_embeddings USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS sentence_embeddings_normalized_speaker_idx
ON sentence_embeddings ((regexp_replace(
    regexp_replace(
      regexp_replace(replace(btrim(speaker), chr(160), ' '), '^(presented by|by)[[:space:]]+', '', 'i'),
      '^(president|elder|sister|brother|bishop)[[:space:]]+', '', 'i'
    ),
    '[[:space:]]+', ' ', 'g'
  )))
WHERE speaker IS NOT NULL;

-- Enable Row Level Security
ALTER TABLE sentence_embeddings ENABLE ROW LEVEL SECURITY;

-- RLS policy: authenticated users can read
DROP POLICY IF EXISTS "Allow authenticated users to read" ON sentence_embeddings;
CREATE POLICY "Allow authenticated users to read"
ON sentence_embeddings FOR SELECT
TO authenticated
USING (true);

-- ============================================
-- Page Views table (PUBLIC access for RLS demo)
-- ============================================
-- This table intentionally has PUBLIC policies so students can
-- contrast it with sentence_embeddings (auth-only).

CREATE TABLE IF NOT EXISTS page_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    visited_at TIMESTAMPTZ DEFAULT NOW(),
    page_url TEXT,
    user_agent TEXT
);

ALTER TABLE page_views ENABLE ROW LEVEL SECURITY;

-- Anyone (including unauthenticated visitors) can insert page views
DROP POLICY IF EXISTS "Allow public inserts" ON page_views;
CREATE POLICY "Allow public inserts"
ON page_views FOR INSERT
TO anon, authenticated
WITH CHECK (true);

-- Anyone can read page views (for the counter)
DROP POLICY IF EXISTS "Allow public reads" ON page_views;
CREATE POLICY "Allow public reads"
ON page_views FOR SELECT
TO anon, authenticated
USING (true);

-- Recreate the function because PostgreSQL cannot change a function's
-- returned columns with CREATE OR REPLACE FUNCTION.
DROP FUNCTION IF EXISTS public.match_sentences(vector, int);
DROP FUNCTION IF EXISTS public.match_sentences(vector, int, text);

-- Create function for similarity search
CREATE OR REPLACE FUNCTION public.match_sentences(
  query_embedding vector(1536),
  match_count int DEFAULT 20,
  speaker_filter text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  talk_id uuid,
  title text,
  speaker text,
  url text,
  text text,
  similarity float
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
  IF speaker_filter IS NULL OR btrim(speaker_filter) = '' THEN
    RETURN QUERY
    SELECT
      se.id, se.talk_id, se.title, se.speaker, se.url, se.text,
      1 - (se.embedding <=> query_embedding) as similarity
    FROM sentence_embeddings AS se
    ORDER BY se.embedding <=> query_embedding
    LIMIT match_count;
  ELSE
    RETURN QUERY
    SELECT
      se.id, se.talk_id, se.title, se.speaker, se.url, se.text,
      1 - (se.embedding <=> query_embedding) as similarity
    FROM sentence_embeddings AS se
    WHERE regexp_replace(
      regexp_replace(
        regexp_replace(replace(btrim(se.speaker), chr(160), ' '), '^(presented by|by)[[:space:]]+', '', 'i'),
        '^(president|elder|sister|brother|bishop)[[:space:]]+', '', 'i'
      ),
      '[[:space:]]+', ' ', 'g'
    ) = speaker_filter
    ORDER BY se.embedding <=> query_embedding
    LIMIT match_count;
  END IF;
END;
$$;

-- Return one row per speaker for the shared search filter.
CREATE OR REPLACE FUNCTION public.get_speakers()
RETURNS TABLE (speaker text)
LANGUAGE sql STABLE
AS $$
  SELECT DISTINCT regexp_replace(
    regexp_replace(
      regexp_replace(replace(btrim(sentence_embeddings.speaker), chr(160), ' '), '^(presented by|by)[[:space:]]+', '', 'i'),
      '^(president|elder|sister|brother|bishop)[[:space:]]+', '', 'i'
    ),
    '[[:space:]]+', ' ', 'g'
  ) AS speaker
  FROM sentence_embeddings
  WHERE sentence_embeddings.speaker IS NOT NULL
    AND btrim(sentence_embeddings.speaker) <> ''
  ORDER BY speaker;
$$;
"""

    url = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query"
    headers = {
        "Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, headers=headers, json={"query": schema_sql})
    if resp.status_code in (200, 201):
        print("✅ Database schema created successfully!")
    else:
        print(f"❌ Schema creation failed: {resp.status_code}")
        print(resp.text[:500])
        return False

    # Verify table exists via PostgREST
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    for attempt in range(5):
        try:
            result = client.table('sentence_embeddings').select('id', count='exact').limit(1).execute()
            print(f"✅ Table verified. Current rows: {result.count or 0}")
            return True
        except Exception:
            if attempt < 4:
                print(f"   Waiting for schema cache to refresh... ({attempt + 1}/5)")
                time.sleep(3)
            else:
                print("⚠️  Table created but PostgREST cache hasn't refreshed yet.")
                print("   This is normal — it should be ready by import time.")
                return True


if __name__ == '__main__':
    if not create_schema():
        sys.exit(1)
    print("\n✅ Schema ready! Next: python scripts/02_scrape_data.py")
