begin;

create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, email, raw_user_meta_data, is_anonymous)
values
  ('00000000-0000-0000-0000-000000000071', 'active-owner@example.com', '{"display_name":"Owner"}', false),
  ('00000000-0000-0000-0000-000000000072', null, '{"display_name":"Member"}', true);

insert into public.rooms (id, owner_id, name)
values (
  '10000000-0000-0000-0000-000000000071',
  '00000000-0000-0000-0000-000000000071',
  'Active ticket room'
);

insert into public.room_members (room_id, user_id, role, display_name)
values
  ('10000000-0000-0000-0000-000000000071', '00000000-0000-0000-0000-000000000071', 'facilitator', 'Owner'),
  ('10000000-0000-0000-0000-000000000071', '00000000-0000-0000-0000-000000000072', 'member', 'Member');

insert into public.tickets (id, room_id, issue_key, summary, position)
values
  ('20000000-0000-0000-0000-000000000071', '10000000-0000-0000-0000-000000000071', 'TT-71', 'First', 0),
  ('20000000-0000-0000-0000-000000000072', '10000000-0000-0000-0000-000000000071', 'TT-72', 'Second', 1);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000071","role":"authenticated"}',
  true
);
update public.rooms
set active_ticket_id = '20000000-0000-0000-0000-000000000071'
where id = '10000000-0000-0000-0000-000000000071';
select is(
  (select active_ticket_id::text from public.rooms),
  '20000000-0000-0000-0000-000000000071',
  'the facilitator can persist the active ticket'
);

select lives_ok(
  $$select * from public.reorder_room_tickets(
    '10000000-0000-0000-0000-000000000071',
    array[
      '20000000-0000-0000-0000-000000000072',
      '20000000-0000-0000-0000-000000000071'
    ]::uuid[]
  )$$,
  'reordering the backlog succeeds while a ticket is active'
);
select is(
  (select active_ticket_id::text from public.rooms),
  '20000000-0000-0000-0000-000000000071',
  'reordering does not change the active ticket identity'
);

select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000072","role":"authenticated","is_anonymous":true}',
  true
);
select is(
  (select active_ticket_id::text from public.rooms),
  '20000000-0000-0000-0000-000000000071',
  'a member can read the shared active ticket'
);
update public.rooms
set active_ticket_id = '20000000-0000-0000-0000-000000000072'
where id = '10000000-0000-0000-0000-000000000071';

reset role;
select is(
  (select active_ticket_id::text from public.rooms where id = '10000000-0000-0000-0000-000000000071'),
  '20000000-0000-0000-0000-000000000071',
  'a member cannot change the active ticket'
);

select * from finish();
rollback;
