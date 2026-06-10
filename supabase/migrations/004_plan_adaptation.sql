-- Run after 003_session_followups.sql

alter table public.plans
  add column if not exists adaptation_log jsonb not null default '[]'::jsonb,
  add column if not exists updated_at timestamptz not null default now();
