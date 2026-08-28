begin;

create extension if not exists pgtap with schema extensions;
select plan(3);

insert into auth.users (id, email, raw_user_meta_data, is_anonymous)
values
  ('00000000-0000-0000-0000-000000000061', 'backlog-owner@example.com', '{"display_name":"Owner"}', false),
  ('00000000-0000-0000-0000-000000000062', null, '{"display_name":"Member"}', true);

insert into public.rooms (id, owner_id, name)
values (
  '10000000-0000-0000-0000-000000000061',
  '00000000-0000-0000-0000-000000000061',
  'Backlog room'
);

insert into public.room_members (room_id, user_id, role, display_name)
values
  ('10000000-0000-0000-0000-000000000061', '00000000-0000-0000-0000-000000000061', 'facilitator', 'Owner'),
  ('10000000-0000-0000-0000-000000000061', '00000000-0000-0000-0000-000000000062', 'member', 'Member');

insert into public.tickets (id, room_id, issue_key, summary, position)
values
  ('20000000-0000-0000-0000-000000000061', '10000000-0000-0000-0000-000000000061', 'TT-61', 'First', 0),
  ('20000000-0000-0000-0000-000000000062', '10000000-0000-0000-0000-000000000061', null, 'Manual', 1),
  ('20000000-0000-0000-0000-000000000063', '10000000-0000-0000-0000-000000000061', 'TT-63', 'Third', 2);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000061","role":"authenticated"}',
  true
);

select lives_ok(
  $$select * from public.reorder_room_tickets(
    '10000000-0000-0000-0000-000000000061',
    array[
      '20000000-0000-0000-0000-000000000063',
      '20000000-0000-0000-0000-000000000061',
      '20000000-0000-0000-0000-000000000062'
    ]::uuid[]
  )$$,
  'the facilitator can reorder every room ticket'
);
select is(
  (select string_agg(coalesce(issue_key, 'manual'), ',' order by position) from public.tickets),
  'TT-63,TT-61,manual',
  'the reordered positions persist, including a ticket without a Jira key'
);

select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000062","role":"authenticated","is_anonymous":true}',
  true
);
select throws_ok(
  $$select * from public.reorder_room_tickets(
    '10000000-0000-0000-0000-000000000061',
    array[
      '20000000-0000-0000-0000-000000000061',
      '20000000-0000-0000-0000-000000000062',
      '20000000-0000-0000-0000-000000000063'
    ]::uuid[]
  )$$,
  '42501',
  'Only the facilitator can reorder tickets',
  'a member cannot reorder the backlog'
);

select * from finish();
rollback;
