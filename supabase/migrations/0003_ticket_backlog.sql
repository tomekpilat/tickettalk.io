alter table public.tickets
  alter column issue_key drop not null;

alter table public.tickets
  drop constraint tickets_issue_key_check;

alter table public.tickets
  add constraint tickets_issue_key_check
  check (issue_key is null or char_length(trim(issue_key)) between 1 and 40);

create unique index tickets_room_issue_key_unique_idx
on public.tickets (room_id, upper(issue_key))
where issue_key is not null;

create or replace function public.reorder_room_tickets(
  p_room_id uuid,
  p_ticket_ids uuid[]
)
returns setof public.tickets
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if auth.role() <> 'service_role' and not public.is_room_owner(p_room_id) then
    raise exception 'Only the facilitator can reorder tickets'
      using errcode = '42501';
  end if;

  if cardinality(p_ticket_ids) <> (
    select count(*)::integer from public.tickets where room_id = p_room_id
  ) or cardinality(p_ticket_ids) <> (
    select count(distinct ticket_id)::integer from unnest(p_ticket_ids) as ticket_id
  ) or exists (
    select 1
    from unnest(p_ticket_ids) as requested(ticket_id)
    where not exists (
      select 1 from public.tickets t
      where t.id = requested.ticket_id and t.room_id = p_room_id
    )
  ) then
    raise exception 'Ticket order must include every room ticket exactly once'
      using errcode = '22023';
  end if;

  update public.tickets
  set position = position + 100000
  where room_id = p_room_id;

  update public.tickets as ticket
  set position = requested.ordinality - 1
  from unnest(p_ticket_ids) with ordinality as requested(ticket_id, ordinality)
  where ticket.id = requested.ticket_id and ticket.room_id = p_room_id;

  return query
  select * from public.tickets
  where room_id = p_room_id
  order by position;
end;
$$;

revoke all on function public.reorder_room_tickets(uuid, uuid[]) from public, anon;
grant execute on function public.reorder_room_tickets(uuid, uuid[])
to authenticated, service_role;
