begin;

create extension if not exists pgtap with schema extensions;
select plan(12);

insert into auth.users (id, email, raw_user_meta_data, is_anonymous)
values
  ('00000000-0000-0000-0000-000000000011', 'owner@example.com', '{"display_name":"Owner"}', false),
  ('00000000-0000-0000-0000-000000000012', null, '{"display_name":"Anonymous member"}', true),
  ('00000000-0000-0000-0000-000000000013', 'outsider@example.com', '{"display_name":"Outsider"}', false),
  ('00000000-0000-0000-0000-000000000014', 'creator@example.com', '{"display_name":"Creator"}', false);

insert into public.rooms (id, owner_id, name)
values
  ('10000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000011', 'Owner room'),
  ('10000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000013', 'Outsider room');

insert into public.room_members (room_id, user_id, role, display_name)
values
  ('10000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000011', 'facilitator', 'Owner'),
  ('10000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000012', 'member', 'Member'),
  ('10000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000013', 'facilitator', 'Outsider');

insert into public.tickets (id, room_id, issue_key, summary, position)
values
  ('20000000-0000-0000-0000-000000000011', '10000000-0000-0000-0000-000000000011', 'TT-11', 'Protected ticket', 0),
  ('20000000-0000-0000-0000-000000000013', '10000000-0000-0000-0000-000000000013', 'TT-13', 'Other room ticket', 0);

update public.rooms
set active_ticket_id = '20000000-0000-0000-0000-000000000011'
where id = '10000000-0000-0000-0000-000000000011';

insert into public.votes (room_id, ticket_id, user_id, value)
values
  ('10000000-0000-0000-0000-000000000011', '20000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000011', '5'),
  ('10000000-0000-0000-0000-000000000011', '20000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000012', '8');

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000014","role":"authenticated"}',
  true
);
select lives_ok(
  $$select * from public.create_room_with_facilitator(
    '00000000-0000-0000-0000-000000000014', 'Creator', 'Atomic room'
  )$$,
  'an authenticated facilitator can create a room'
);
reset role;
select ok(
  exists (
    select 1
    from public.rooms r
    join public.room_members rm on rm.room_id = r.id
    where r.owner_id = '00000000-0000-0000-0000-000000000014'
      and rm.user_id = r.owner_id
      and rm.role = 'facilitator'
  ),
  'room creation atomically inserts the facilitator membership'
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000011","role":"authenticated"}',
  true
);

select is((select count(*) from public.rooms)::bigint, 1::bigint, 'cross-room reads are denied');
select is((select count(*) from public.tickets)::bigint, 1::bigint, 'cross-room ticket reads are denied');
select is((select count(*) from public.votes)::bigint, 1::bigint, 'another unrevealed vote is hidden');
select is((select value from public.votes limit 1), '5', 'the voter can read their own vote');

update public.rooms
set name = 'Changed'
where id = '10000000-0000-0000-0000-000000000013';

reset role;
select is(
  (select name from public.rooms where id = '10000000-0000-0000-0000-000000000013'),
  'Outsider room',
  'a user cannot update another room'
);

update public.votes
set revealed = true
where room_id = '10000000-0000-0000-0000-000000000011';
set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000012","role":"authenticated","is_anonymous":true}',
  true
);

select is((select count(*) from public.rooms)::bigint, 1::bigint, 'an anonymous member can read their room');
select is((select count(*) from public.votes)::bigint, 2::bigint, 'revealed room votes are visible');

update public.rooms
set name = 'Member changed it'
where id = '10000000-0000-0000-0000-000000000011';

reset role;
select is(
  (select name from public.rooms where id = '10000000-0000-0000-0000-000000000011'),
  'Owner room',
  'an anonymous member cannot change room settings'
);

select ok(
  (select reloptions @> array['security_invoker=true'] from pg_class where relname = 'room_rollups'),
  'the room rollup view preserves RLS'
);

select ok(
  not has_table_privilege('authenticated', 'public.jira_room_connections', 'select'),
  'browser clients cannot read encrypted Jira credentials'
);

select * from finish();
rollback;
