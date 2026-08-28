create table public.vote_statuses (
  room_id uuid not null,
  ticket_id uuid not null,
  user_id uuid not null references public.profiles(id) on delete cascade,
  updated_at timestamptz not null default now(),
  primary key (ticket_id, user_id),
  foreign key (ticket_id, room_id)
    references public.tickets(id, room_id) on delete cascade
);

create index vote_statuses_room_ticket_idx
on public.vote_statuses (room_id, ticket_id);

create or replace function public.sync_vote_status()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if tg_op = 'DELETE' then
    delete from public.vote_statuses
    where ticket_id = old.ticket_id and user_id = old.user_id;
    return old;
  end if;

  insert into public.vote_statuses (room_id, ticket_id, user_id, updated_at)
  values (new.room_id, new.ticket_id, new.user_id, new.updated_at)
  on conflict (ticket_id, user_id) do update
    set room_id = excluded.room_id,
        updated_at = excluded.updated_at;
  return new;
end;
$$;

create trigger votes_sync_safe_status
after insert or update or delete on public.votes
for each row execute function public.sync_vote_status();

insert into public.vote_statuses (room_id, ticket_id, user_id, updated_at)
select room_id, ticket_id, user_id, updated_at
from public.votes
on conflict (ticket_id, user_id) do update
  set room_id = excluded.room_id,
      updated_at = excluded.updated_at;

alter table public.vote_statuses enable row level security;

create policy "members read safe vote statuses"
on public.vote_statuses for select to authenticated
using (public.is_room_member(room_id) or public.is_room_owner(room_id));

grant select on public.vote_statuses to authenticated;
grant select, insert, update, delete on public.vote_statuses to service_role;

drop policy "voters submit their vote" on public.votes;
create policy "voters submit an active scale vote"
on public.votes for insert to authenticated
with check (
  user_id = auth.uid()
  and public.is_room_member(room_id)
  and exists (
    select 1
    from public.rooms r
    join public.tickets t on t.id = ticket_id and t.room_id = r.id
    where r.id = room_id
      and r.active_ticket_id = ticket_id
      and value = any (
        case r.scale
          when 'fibonacci' then array['0', '1', '2', '3', '5', '8', '13', '21', '?']
          when 'extended' then array['1', '2', '3', '5', '8', '13', '21', '34', '55', '?']
          else array['XS', 'S', 'M', 'L', 'XL', '?']
        end
      )
  )
);

drop policy "voters update an unrevealed vote" on public.votes;
create policy "voters update their active unrevealed vote"
on public.votes for update to authenticated
using (user_id = auth.uid() and not revealed)
with check (
  user_id = auth.uid()
  and not revealed
  and public.is_room_member(room_id)
  and exists (
    select 1
    from public.rooms r
    where r.id = room_id
      and r.active_ticket_id = ticket_id
      and value = any (
        case r.scale
          when 'fibonacci' then array['0', '1', '2', '3', '5', '8', '13', '21', '?']
          when 'extended' then array['1', '2', '3', '5', '8', '13', '21', '34', '55', '?']
          else array['XS', 'S', 'M', 'L', 'XL', '?']
        end
      )
  )
);

do $$
begin
  if exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'votes'
  ) then
    alter publication supabase_realtime drop table public.votes;
  end if;
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'vote_statuses'
  ) then
    alter publication supabase_realtime add table public.vote_statuses;
  end if;
end;
$$;
