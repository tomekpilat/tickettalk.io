create extension if not exists "pgcrypto";

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  created_at timestamptz not null default now()
);

create table public.rooms (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references public.profiles(id) on delete cascade,
  name text not null,
  scale text not null default 'fibonacci' check (scale in ('fibonacci', 'extended', 'tshirt')),
  reveal_mode text not null default 'manual' check (reveal_mode in ('manual', 'auto')),
  created_at timestamptz not null default now()
);

create table public.room_members (
  room_id uuid references public.rooms(id) on delete cascade,
  user_id uuid references public.profiles(id) on delete cascade,
  display_name text not null,
  primary key (room_id, user_id)
);

create table public.tickets (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references public.rooms(id) on delete cascade,
  issue_key text not null,
  summary text not null,
  issue_type text not null default 'Story',
  description text not null default '',
  story_points numeric,
  position integer not null default 0,
  created_at timestamptz not null default now()
);

create table public.votes (
  ticket_id uuid references public.tickets(id) on delete cascade,
  user_id uuid references public.profiles(id) on delete cascade,
  value text not null,
  revealed boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (ticket_id, user_id)
);

create function public.is_room_member(check_room_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.room_members
    where room_id = check_room_id and user_id = auth.uid()
  );
$$;

create function public.is_room_owner(check_room_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.rooms
    where id = check_room_id and owner_id = auth.uid()
  );
$$;

create view public.room_rollups with (security_invoker = true) as
select r.*,
  count(t.id)::integer as ticket_count,
  count(t.story_points)::integer as sized_count,
  coalesce(sum(t.story_points), 0)::float as total_points
from public.rooms r
left join public.tickets t on t.room_id = r.id
group by r.id;

alter table public.profiles enable row level security;
alter table public.rooms enable row level security;
alter table public.room_members enable row level security;
alter table public.tickets enable row level security;
alter table public.votes enable row level security;

create policy "profiles are readable by signed-in users" on public.profiles for select to authenticated using (true);
create policy "users create their profile" on public.profiles for insert to authenticated with check (id = auth.uid());
create policy "users update their profile" on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
create policy "owners manage rooms" on public.rooms for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "members read rooms" on public.rooms for select to authenticated using (
  public.is_room_member(id)
);
create policy "members read the room roster" on public.room_members for select to authenticated using (
  public.is_room_member(room_id) or public.is_room_owner(room_id)
);
create policy "owners manage the room roster" on public.room_members for all to authenticated using (
  public.is_room_owner(room_id)
) with check (public.is_room_owner(room_id));
create policy "members read tickets" on public.tickets for select to authenticated using (
  public.is_room_member(room_id) or public.is_room_owner(room_id)
);
create policy "members update tickets" on public.tickets for update to authenticated using (
  public.is_room_member(room_id) or public.is_room_owner(room_id)
) with check (public.is_room_member(room_id) or public.is_room_owner(room_id));
create policy "owners create and remove tickets" on public.tickets for all to authenticated using (
  public.is_room_owner(room_id)
) with check (public.is_room_owner(room_id));
create policy "voters submit their vote" on public.votes for insert to authenticated with check (
  user_id = auth.uid() and exists (
    select 1 from public.tickets t
    where t.id = ticket_id
      and (public.is_room_member(t.room_id) or public.is_room_owner(t.room_id))
  )
);
create policy "voters update their vote" on public.votes for update to authenticated using (user_id = auth.uid()) with check (
  user_id = auth.uid() and exists (
    select 1 from public.tickets t
    where t.id = ticket_id
      and (public.is_room_member(t.room_id) or public.is_room_owner(t.room_id))
  )
);
create policy "voters remove their vote" on public.votes for delete to authenticated using (user_id = auth.uid());
create policy "members read revealed votes" on public.votes for select to authenticated using (
  user_id = auth.uid() or (
    revealed and exists (
      select 1 from public.tickets t
      where t.id = ticket_id
        and (public.is_room_member(t.room_id) or public.is_room_owner(t.room_id))
    )
  )
);

alter publication supabase_realtime add table public.room_members;
alter publication supabase_realtime add table public.votes;
