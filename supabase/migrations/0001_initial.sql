create extension if not exists "pgcrypto";

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(trim(display_name)) between 1 and 80),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.rooms (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 3 and 120),
  scale text not null default 'fibonacci'
    check (scale in ('fibonacci', 'extended', 'tshirt')),
  reveal_mode text not null default 'manual'
    check (reveal_mode in ('manual', 'auto')),
  active_ticket_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.room_members (
  room_id uuid not null references public.rooms(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('facilitator', 'member')),
  display_name text not null check (char_length(trim(display_name)) between 1 and 80),
  joined_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  primary key (room_id, user_id)
);

create table public.tickets (
  id uuid primary key default gen_random_uuid(),
  room_id uuid not null references public.rooms(id) on delete cascade,
  issue_key text not null check (char_length(trim(issue_key)) between 1 and 40),
  summary text not null check (char_length(trim(summary)) between 1 and 500),
  issue_type text not null default 'Story',
  description text not null default '',
  story_points numeric check (story_points is null or story_points between 0 and 1000),
  position integer not null default 0 check (position >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, room_id),
  unique (room_id, position)
);

alter table public.rooms
  add constraint rooms_active_ticket_fk
  foreign key (active_ticket_id) references public.tickets(id) on delete set null;

create table public.votes (
  room_id uuid not null,
  ticket_id uuid not null,
  user_id uuid not null references public.profiles(id) on delete cascade,
  value text not null check (char_length(value) between 1 and 8),
  revealed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (ticket_id, user_id),
  foreign key (ticket_id, room_id)
    references public.tickets(id, room_id) on delete cascade
);

create index rooms_owner_created_idx on public.rooms (owner_id, created_at desc);
create index room_members_user_room_idx on public.room_members (user_id, room_id);
create index tickets_room_position_idx on public.tickets (room_id, position);
create index votes_room_ticket_idx on public.votes (room_id, ticket_id);
create index votes_ticket_revealed_idx on public.votes (ticket_id, revealed);

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create trigger rooms_set_updated_at
before update on public.rooms
for each row execute function public.set_updated_at();

create trigger tickets_set_updated_at
before update on public.tickets
for each row execute function public.set_updated_at();

create trigger votes_set_updated_at
before update on public.votes
for each row execute function public.set_updated_at();

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(
      nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
      nullif(split_part(coalesce(new.email, ''), '@', 1), ''),
      'Guest'
    )
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_auth_user();

create or replace function public.is_room_member(check_room_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.room_members
    where room_id = check_room_id and user_id = auth.uid()
  );
$$;

create or replace function public.is_room_owner(check_room_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.rooms
    where id = check_room_id and owner_id = auth.uid()
  );
$$;

create or replace function public.create_room_with_facilitator(
  p_owner_id uuid,
  p_display_name text,
  p_name text,
  p_scale text default 'fibonacci',
  p_reveal_mode text default 'manual'
)
returns table (
  id uuid,
  owner_id uuid,
  name text,
  scale text,
  reveal_mode text,
  active_ticket_id uuid,
  created_at timestamptz,
  updated_at timestamptz,
  ticket_count integer,
  sized_count integer,
  total_points double precision
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  created_room public.rooms%rowtype;
begin
  if auth.role() <> 'service_role' and auth.uid() is distinct from p_owner_id then
    raise exception 'A room can only be created for the authenticated user'
      using errcode = '42501';
  end if;

  insert into public.profiles (id, display_name)
  values (p_owner_id, trim(p_display_name))
  on conflict on constraint profiles_pkey do update
    set display_name = excluded.display_name;

  insert into public.rooms (owner_id, name, scale, reveal_mode)
  values (p_owner_id, trim(p_name), p_scale, p_reveal_mode)
  returning * into created_room;

  insert into public.room_members (room_id, user_id, role, display_name)
  values (created_room.id, p_owner_id, 'facilitator', trim(p_display_name));

  return query
  select
    created_room.id,
    created_room.owner_id,
    created_room.name,
    created_room.scale,
    created_room.reveal_mode,
    created_room.active_ticket_id,
    created_room.created_at,
    created_room.updated_at,
    0,
    0,
    0::double precision;
end;
$$;

create view public.room_rollups
with (security_invoker = true)
as
select
  r.*,
  count(t.id)::integer as ticket_count,
  count(t.story_points)::integer as sized_count,
  coalesce(sum(t.story_points), 0)::double precision as total_points
from public.rooms r
left join public.tickets t on t.room_id = r.id
group by r.id;

alter table public.profiles enable row level security;
alter table public.rooms enable row level security;
alter table public.room_members enable row level security;
alter table public.tickets enable row level security;
alter table public.votes enable row level security;

create policy "users read their profile"
on public.profiles for select to authenticated
using (id = auth.uid());

create policy "users update their profile"
on public.profiles for update to authenticated
using (id = auth.uid())
with check (id = auth.uid());

create policy "owners create rooms"
on public.rooms for insert to authenticated
with check (owner_id = auth.uid());

create policy "members read rooms"
on public.rooms for select to authenticated
using (owner_id = auth.uid() or public.is_room_member(id));

create policy "owners update rooms"
on public.rooms for update to authenticated
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

create policy "owners delete rooms"
on public.rooms for delete to authenticated
using (owner_id = auth.uid());

create policy "members read the room roster"
on public.room_members for select to authenticated
using (public.is_room_member(room_id) or public.is_room_owner(room_id));

create policy "owners manage the room roster"
on public.room_members for all to authenticated
using (public.is_room_owner(room_id))
with check (public.is_room_owner(room_id));

create policy "members read tickets"
on public.tickets for select to authenticated
using (public.is_room_member(room_id) or public.is_room_owner(room_id));

create policy "owners create tickets"
on public.tickets for insert to authenticated
with check (public.is_room_owner(room_id));

create policy "owners update tickets"
on public.tickets for update to authenticated
using (public.is_room_owner(room_id))
with check (public.is_room_owner(room_id));

create policy "owners delete tickets"
on public.tickets for delete to authenticated
using (public.is_room_owner(room_id));

create policy "voters submit their vote"
on public.votes for insert to authenticated
with check (
  user_id = auth.uid()
  and public.is_room_member(room_id)
  and exists (
    select 1 from public.tickets t
    where t.id = ticket_id and t.room_id = room_id
  )
);

create policy "voters update an unrevealed vote"
on public.votes for update to authenticated
using (user_id = auth.uid() and not revealed)
with check (user_id = auth.uid() and not revealed and public.is_room_member(room_id));

create policy "voters remove an unrevealed vote"
on public.votes for delete to authenticated
using (user_id = auth.uid() and not revealed);

create policy "members read their own or revealed votes"
on public.votes for select to authenticated
using (
  public.is_room_member(room_id)
  and (user_id = auth.uid() or revealed)
);

grant select, update on public.profiles to authenticated;
grant select, insert, update, delete on public.rooms to authenticated;
grant select, insert, update, delete on public.room_members to authenticated;
grant select, insert, update, delete on public.tickets to authenticated;
grant select, insert, update, delete on public.votes to authenticated;
grant select on public.room_rollups to authenticated;

revoke all on function public.create_room_with_facilitator(uuid, text, text, text, text)
from public, anon;
grant execute on function public.create_room_with_facilitator(uuid, text, text, text, text)
to authenticated, service_role;
revoke all on function public.is_room_member(uuid) from public, anon;
revoke all on function public.is_room_owner(uuid) from public, anon;
grant execute on function public.is_room_member(uuid) to authenticated, service_role;
grant execute on function public.is_room_owner(uuid) to authenticated, service_role;

do $$
declare
  realtime_table text;
begin
  foreach realtime_table in array array['rooms', 'room_members', 'tickets', 'votes']
  loop
    if not exists (
      select 1
      from pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = realtime_table
    ) then
      execute format('alter publication supabase_realtime add table public.%I', realtime_table);
    end if;
  end loop;
end;
$$;
