begin;

create extension if not exists pgtap with schema extensions;
select plan(9);

insert into auth.users (id, email, raw_user_meta_data, is_anonymous)
values
  ('00000000-0000-0000-0000-000000000081', 'vote-owner@example.com', '{"display_name":"Owner"}', false),
  ('00000000-0000-0000-0000-000000000082', null, '{"display_name":"Member"}', true),
  ('00000000-0000-0000-0000-000000000083', null, '{"display_name":"Outsider"}', true);

insert into public.rooms (id, owner_id, name, active_ticket_id)
values (
  '10000000-0000-0000-0000-000000000081',
  '00000000-0000-0000-0000-000000000081',
  'Secret vote room',
  null
);

insert into public.room_members (room_id, user_id, role, display_name)
values
  ('10000000-0000-0000-0000-000000000081', '00000000-0000-0000-0000-000000000081', 'facilitator', 'Owner'),
  ('10000000-0000-0000-0000-000000000081', '00000000-0000-0000-0000-000000000082', 'member', 'Member');

insert into public.tickets (id, room_id, issue_key, summary, position)
values
  ('20000000-0000-0000-0000-000000000081', '10000000-0000-0000-0000-000000000081', 'TT-81', 'Active', 0),
  ('20000000-0000-0000-0000-000000000082', '10000000-0000-0000-0000-000000000081', 'TT-82', 'Inactive', 1);

update public.rooms
set active_ticket_id = '20000000-0000-0000-0000-000000000081'
where id = '10000000-0000-0000-0000-000000000081';

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000082","role":"authenticated","is_anonymous":true}',
  true
);

select lives_ok(
  $$insert into public.votes (room_id, ticket_id, user_id, value)
    values (
      '10000000-0000-0000-0000-000000000081',
      '20000000-0000-0000-0000-000000000081',
      '00000000-0000-0000-0000-000000000082',
      '8'
    )$$,
  'a member can vote on the active ticket'
);
select lives_ok(
  $$update public.votes set value = '13'
    where ticket_id = '20000000-0000-0000-0000-000000000081'
      and user_id = '00000000-0000-0000-0000-000000000082'$$,
  'a member can replace their own unrevealed vote'
);
select is((select count(*) from public.votes)::bigint, 1::bigint, 'upsert semantics keep one current vote');
select is((select value from public.votes), '13', 'the voter can read their own value');
select is((select count(*) from public.vote_statuses)::bigint, 1::bigint, 'the safe voted status is visible');

select throws_ok(
  $$insert into public.votes (room_id, ticket_id, user_id, value)
    values (
      '10000000-0000-0000-0000-000000000081',
      '20000000-0000-0000-0000-000000000082',
      '00000000-0000-0000-0000-000000000082',
      '5'
  )$$,
  '42501',
  'new row violates row-level security policy for table "votes"',
  'a member cannot vote on an inactive ticket'
);

select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000081","role":"authenticated"}',
  true
);
select is((select count(*) from public.votes)::bigint, 0::bigint, 'the facilitator cannot read a member unrevealed value');
select is((select count(*) from public.vote_statuses)::bigint, 1::bigint, 'the facilitator can read voted status without value');

select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000083","role":"authenticated","is_anonymous":true}',
  true
);
select is((select count(*) from public.vote_statuses)::bigint, 0::bigint, 'a non-member cannot read voted statuses');

select * from finish();
rollback;
