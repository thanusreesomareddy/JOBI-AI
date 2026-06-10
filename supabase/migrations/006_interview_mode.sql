-- Run after 005_session_adapt_plan.sql

alter table public.sessions
  add column if not exists interview_log jsonb not null default '[]'::jsonb,
  add column if not exists session_mode text not null default 'interview'
    check (session_mode in ('standard', 'interview'));
