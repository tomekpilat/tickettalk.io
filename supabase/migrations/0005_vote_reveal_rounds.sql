alter table public.tickets
  add column final_estimate text,
  add column vote_state text not null default 'voting'
    check (vote_state in ('voting', 'revealed')),
  add column vote_round integer not null default 1 check (vote_round > 0),
  add column revealed_at timestamptz,
  add column revealed_by uuid references public.profiles(id) on delete set null;

create or replace function public.guard_open_vote()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if not exists (
    select 1
    from public.tickets t
    join public.rooms r on r.id = t.room_id
    where t.id = new.ticket_id
      and t.room_id = new.room_id
      and t.vote_state = 'voting'
      and r.active_ticket_id = t.id
  ) then
    raise exception 'Voting is open only for the active unrevealed ticket'
      using errcode = '55000';
  end if;
  return new;
end;
$$;

create trigger votes_require_open_round
before insert or update of value on public.votes
for each row execute function public.guard_open_vote();

create or replace function public.maybe_auto_reveal_votes()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  room_row public.rooms%rowtype;
  ticket_state text;
  eligible_count integer;
  voted_count integer;
begin
  select r.* into room_row
  from public.rooms r
  where r.id = new.room_id
  for update;

  select vote_state into ticket_state
  from public.tickets
  where id = new.ticket_id and room_id = new.room_id;

  if room_row.reveal_mode <> 'auto'
    or room_row.active_ticket_id is distinct from new.ticket_id
    or ticket_state <> 'voting' then
    return new;
  end if;

  select count(*)::integer into eligible_count
  from public.room_members
  where room_id = new.room_id
    and last_seen_at >= now() - interval '45 seconds';

  select count(*)::integer into voted_count
  from public.votes v
  join public.room_members rm
    on rm.room_id = v.room_id and rm.user_id = v.user_id
  where v.room_id = new.room_id
    and v.ticket_id = new.ticket_id
    and rm.last_seen_at >= now() - interval '45 seconds';

  if eligible_count > 0 and voted_count >= eligible_count then
    update public.votes
    set revealed = true
    where room_id = new.room_id and ticket_id = new.ticket_id;

    update public.tickets
    set vote_state = 'revealed', revealed_at = now(), revealed_by = null
    where id = new.ticket_id and vote_state = 'voting';
  end if;
  return new;
end;
$$;

create trigger votes_maybe_auto_reveal
after insert or update of value on public.votes
for each row execute function public.maybe_auto_reveal_votes();

create or replace function public.reveal_ticket_votes(
  p_room_id uuid,
  p_ticket_id uuid,
  p_actor_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  owner_id uuid;
  current_state text;
begin
  if auth.role() <> 'service_role' and auth.uid() is distinct from p_actor_id then
    raise exception 'Cannot reveal for another user' using errcode = '42501';
  end if;

  select r.owner_id, t.vote_state into owner_id, current_state
  from public.tickets t
  join public.rooms r on r.id = t.room_id
  where t.id = p_ticket_id
    and t.room_id = p_room_id
    and r.active_ticket_id = t.id
  for update of t;

  if owner_id is null then
    raise exception 'Active ticket not found' using errcode = 'P0002';
  end if;
  if owner_id is distinct from p_actor_id then
    raise exception 'Only the facilitator can reveal votes' using errcode = '42501';
  end if;
  if current_state = 'revealed' then
    return false;
  end if;
  if not exists (
    select 1 from public.votes
    where room_id = p_room_id and ticket_id = p_ticket_id
  ) then
    raise exception 'At least one vote is required' using errcode = '22023';
  end if;

  update public.votes
  set revealed = true
  where room_id = p_room_id and ticket_id = p_ticket_id;

  update public.tickets
  set vote_state = 'revealed', revealed_at = now(), revealed_by = p_actor_id
  where id = p_ticket_id;
  return true;
end;
$$;

create or replace function public.restart_ticket_vote(
  p_room_id uuid,
  p_ticket_id uuid,
  p_actor_id uuid
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  owner_id uuid;
  next_round integer;
begin
  if auth.role() <> 'service_role' and auth.uid() is distinct from p_actor_id then
    raise exception 'Cannot restart for another user' using errcode = '42501';
  end if;

  select r.owner_id, t.vote_round + 1 into owner_id, next_round
  from public.tickets t
  join public.rooms r on r.id = t.room_id
  where t.id = p_ticket_id and t.room_id = p_room_id
  for update of t;

  if owner_id is null then
    raise exception 'Ticket not found' using errcode = 'P0002';
  end if;
  if owner_id is distinct from p_actor_id then
    raise exception 'Only the facilitator can restart voting' using errcode = '42501';
  end if;

  delete from public.votes
  where room_id = p_room_id and ticket_id = p_ticket_id;

  update public.tickets
  set vote_state = 'voting',
      vote_round = next_round,
      revealed_at = null,
      revealed_by = null,
      final_estimate = null
  where id = p_ticket_id;
  return next_round;
end;
$$;

revoke all on function public.reveal_ticket_votes(uuid, uuid, uuid) from public, anon;
revoke all on function public.restart_ticket_vote(uuid, uuid, uuid) from public, anon;
grant execute on function public.reveal_ticket_votes(uuid, uuid, uuid) to service_role;
grant execute on function public.restart_ticket_vote(uuid, uuid, uuid) to service_role;

drop view public.room_rollups;
create view public.room_rollups
with (security_invoker = true)
as
select
  r.*,
  count(t.id)::integer as ticket_count,
  count(t.final_estimate)::integer as sized_count,
  coalesce(sum(
    case when t.final_estimate ~ '^[0-9]+([.][0-9]+)?$'
      then t.final_estimate::double precision else 0 end
  ), 0)::double precision as total_points
from public.rooms r
left join public.tickets t on t.room_id = r.id
group by r.id;

grant select on public.room_rollups to authenticated, service_role;
