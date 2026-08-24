-- Beatitude Engine audit trail: verdicts, signoffs, seals.
--
-- Policy encoded in the schema:
--   * every review() call writes one verdicts row (the audit trail);
--   * a seal REQUIRES a verdict (FK) and, in application code, a human
--     'approve' row in signoffs — no verdict, no seal; no sign-off, no seal;
--   * one seal per verdict (UNIQUE on seals.verdict_id).
--
-- RLS is enabled with no policies: only the service-role key (server-side)
-- can touch these tables; anon/authenticated clients get nothing.

create table public.verdicts (
    verdict_id     uuid primary key default gen_random_uuid(),
    artifact_type  text not null,
    artifact       text not null,
    context        jsonb not null default '{}'::jsonb,
    scores         jsonb not null,
    verdict        text not null check (verdict in ('Aligned', 'Closely Aligned', 'Misaligned')),
    rationale      text not null default '',
    suggested_fixes jsonb not null default '{}'::jsonb,
    models_used    jsonb not null default '[]'::jsonb,
    raw_responses  jsonb not null default '[]'::jsonb,
    rubric_version text not null default '1.0',
    created_at     timestamptz not null default now()
);

create index verdicts_created_at_idx on public.verdicts (created_at desc);
create index verdicts_verdict_idx on public.verdicts (verdict);

create table public.signoffs (
    id         uuid primary key default gen_random_uuid(),
    verdict_id uuid not null references public.verdicts (verdict_id),
    approver   text not null,
    decision   text not null check (decision in ('approve', 'reject')),
    note       text not null default '',
    created_at timestamptz not null default now()
);

create index signoffs_verdict_id_idx on public.signoffs (verdict_id);

create table public.seals (
    seal_id    uuid primary key default gen_random_uuid(),
    verdict_id uuid not null unique references public.verdicts (verdict_id),
    signoff_id uuid not null references public.signoffs (id),
    approver   text not null,
    created_at timestamptz not null default now()
);

alter table public.verdicts enable row level security;
alter table public.signoffs enable row level security;
alter table public.seals enable row level security;

comment on table public.verdicts is 'Beatitude Engine audit trail: one row per review() call, written before the verdict is returned.';
comment on table public.signoffs is 'Human sign-off queue: a decision=approve row is the precondition for issue_seal().';
comment on table public.seals is 'Issued "Beatitude Reviewed" seals; each points back at its verdict and the human sign-off that authorized it.';
