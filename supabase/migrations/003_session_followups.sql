-- Run after 002_sessions.sql

alter table public.sessions
  add column if not exists current_prompt text,
  add column if not exists turn_count int not null default 0,
  add column if not exists max_turns int not null default 4,
  add column if not exists session_summary jsonb;
