-- Run after 004_plan_adaptation.sql

alter table public.sessions
  add column if not exists adapt_plan boolean not null default true;
