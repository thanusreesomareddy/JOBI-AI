-- Run in Supabase SQL Editor (Dashboard → SQL → New query)

create extension if not exists "pgcrypto";

create table if not exists public.candidates (
  id uuid primary key default gen_random_uuid(),
  email text,
  created_at timestamptz not null default now()
);

create table if not exists public.resumes (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.candidates (id) on delete cascade,
  raw_text text,
  parsed_json jsonb,
  file_path text,
  created_at timestamptz not null default now()
);

create index if not exists resumes_candidate_id_idx on public.resumes (candidate_id);

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.candidates (id) on delete cascade,
  target_role text not null,
  days int not null check (days > 0),
  plan_json jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists plans_candidate_id_idx on public.plans (candidate_id);

-- Prototype: backend uses service role key; tighten RLS before production.
alter table public.candidates enable row level security;
alter table public.resumes enable row level security;
alter table public.plans enable row level security;
