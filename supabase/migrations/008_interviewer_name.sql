-- Run after 007_interview_phase.sql

alter table public.sessions
  add column if not exists interviewer_name text not null default 'Alex';
