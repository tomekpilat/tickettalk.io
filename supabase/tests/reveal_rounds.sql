begin;

create extension if not exists pgtap with schema extensions;
select plan(10);

insert into auth.users (id, email, raw_user_meta_data, is_anonymous)
values
  ('00000000-0000-0000-0000-000000000091', 'reveal-owner@example.com', '{"display_name":"Owner"}', false),
  ('00000000-0000-0000-0000-000000000092', null, '{"display_name":"Member"}', true),
  ('00000000-0000-0000-0000-000000000093', null, '{"display_name":"Offline"}', true);

insert into public.rooms (id, owner_id, name, reveal_mode)
values
  ('10000000-0000-0000-0000-000000000091', '00000000-0000-0000-0000-000000000091', 'Manual reveal', 'manual'),
  ('10000000-0000-0000-0000-000000000092', '00000000-0000-0000-0000-000000000091', 'Auto reveal', 'auto');

insert into public.room_members (room_id, user_id, role, display_name, last_seen_at)
values
  ('10000000-0000-0000-0000-000000000091', '00000000-0000-0000-0000-000000000091', 'facilitator', 'Owner', now()),
  ('10000000-0000-0000-0000-000000000091', '00000000-0000-0000-0000-000000000092', 'member', 'Member', now()),
  ('10000000-0000-0000-0000-000000000092', '00000000-0000-0000-0000-000000000091', 'facilitator', 'Owner', now()),
  ('10000000-0000-0000-0000-000000000092', '00000000-0000-0000-0000-000000000092', 'member', 'Member', now()),
  ('10000000-0000-0000-0000-000000000092', '00000000-0000-0000-0000-000000000093', 'member', 'Offline', now() - interval '2 minutes');

insert into public.tickets (id, room_id, issue_key, summary, position)
values
  ('20000000-0000-0000-0000-000000000091', '10000000-0000-0000-0000-000000000091', 'TT-91', 'Manual ticket', 0),
  ('20000000-0000-0000-0000-000000000092', '10000000-0000-0000-0000-000000000092', 'TT-92', 'Auto ticket', 0);

update public.rooms set active_ticket_id = '20000000-0000-0000-0000-000000000091'
where id = '10000000-0000-0000-0000-000000000091';
update public.rooms set active_ticket_id = '20000000-0000-0000-0000-000000000092'
where id = '10000000-0000-0000-0000-000000000092';

insert into public.votes (room_id, ticket_id, user_id, value)
values
  ('10000000-0000-0000-0000-000000000091', '20000000-0000-0000-0000-000000000091', '00000000-0000-0000-0000-000000000091', '5'),
  ('10000000-0000-0000-0000-000000000091', '20000000-0000-0000-0000-000000000091', '00000000-0000-0000-0000-000000000092', '8');

set local role service_role;
select is(
  public.reveal_ticket_votes(
    '10000000-0000-0000-0000-000000000091',
    '20000000-0000-0000-0000-000000000091',
    '00000000-0000-0000-0000-000000000091'
  ),
  true,
  'manual reveal performs the transition'
);
select is((select vote_state from public.tickets where id = '20000000-0000-0000-0000-000000000091'), 'revealed', 'ticket reveal state persists');
select is((select count(*) from public.votes where ticket_id = '20000000-0000-0000-0000-000000000091' and revealed)::bigint, 2::bigint, 'all ticket votes reveal together');
select is(
  public.reveal_ticket_votes(
    '10000000-0000-0000-0000-000000000091',
    '20000000-0000-0000-0000-000000000091',
    '00000000-0000-0000-0000-000000000091'
  ),
  false,
  'a duplicate reveal is idempotent'
);
select is(
  public.restart_ticket_vote(
    '10000000-0000-0000-0000-000000000091',
    '20000000-0000-0000-0000-000000000091',
    '00000000-0000-0000-0000-000000000091'
  ),
  2,
  're-vote increments the durable round'
);
select is((select count(*) from public.votes where ticket_id = '20000000-0000-0000-0000-000000000091')::bigint, 0::bigint, 're-vote clears prior values');
select is((select vote_state from public.tickets where id = '20000000-0000-0000-0000-000000000091'), 'voting', 're-vote reopens voting');

insert into public.votes (room_id, ticket_id, user_id, value)
values ('10000000-0000-0000-0000-000000000092', '20000000-0000-0000-0000-000000000092', '00000000-0000-0000-0000-000000000091', '5');
select is((select vote_state from public.tickets where id = '20000000-0000-0000-0000-000000000092'), 'voting', 'auto mode waits for every online member');

insert into public.votes (room_id, ticket_id, user_id, value)
values ('10000000-0000-0000-0000-000000000092', '20000000-0000-0000-0000-000000000092', '00000000-0000-0000-0000-000000000092', '8');
select is((select vote_state from public.tickets where id = '20000000-0000-0000-0000-000000000092'), 'revealed', 'the final online vote reveals exactly once');
select is((select count(*) from public.votes where ticket_id = '20000000-0000-0000-0000-000000000092' and revealed)::bigint, 2::bigint, 'an offline member does not block or create a partial reveal');

select * from finish();
rollback;
