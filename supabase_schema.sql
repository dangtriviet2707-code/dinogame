-- Chạy một lần trong Supabase Dashboard -> SQL Editor.
-- Chỉ backend Flask sử dụng service_role key; không đưa key này vào frontend.
create table if not exists public.dino_players (
    id text primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);

create index if not exists dino_players_updated_at_idx
    on public.dino_players (updated_at desc);

alter table public.dino_players enable row level security;

-- Không cấp quyền đọc/ghi cho client anon/authenticated.
revoke all on table public.dino_players from anon, authenticated;
grant all on table public.dino_players to service_role;

-- Cập nhật updated_at tự động khi upsert.
create or replace function public.set_dino_players_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_dino_players_updated_at on public.dino_players;
create trigger trg_dino_players_updated_at
before update on public.dino_players
for each row execute function public.set_dino_players_updated_at();
