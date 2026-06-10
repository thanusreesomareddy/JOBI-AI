-- Run after 006_interview_mode.sql

alter table public.sessions
  add column if not exists interview_phase text not null default 'lobby'
    check (interview_phase in ('lobby', 'greeting', 'interview'));
