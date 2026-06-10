-- Run in Supabase SQL Editor after 001_initial.sql

create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.candidates (id) on delete cascade,
  plan_id uuid not null references public.plans (id) on delete cascade,
  day int not null check (day > 0),
  prompt_index int not null default 0,
  status text not null default 'in_progress' check (status in ('in_progress', 'completed')),
  turns jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sessions_candidate_id_idx on public.sessions (candidate_id);
create index if not exists sessions_plan_id_idx on public.sessions (plan_id);

alter table public.sessions enable row level security;
