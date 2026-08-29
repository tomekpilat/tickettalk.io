begin;

create extension if not exists pgtap with schema extensions;
select plan(3);

insert into auth.users (id, email, raw_user_meta_data, is_anonymous)
values
  ('00000000-0000-0000-0000-000000000021', 'owner-privacy@example.com', '{"display_name":"Owner"}', false),
  ('00000000-0000-0000-0000-000000000022', null, '{"display_name":"Outsider"}', true);

insert into public.rooms (id, owner_id, name)
values (
  '10000000-0000-0000-0000-000000000021',
  '00000000-0000-0000-0000-000000000021',
  'Private room'
);

insert into public.room_members (room_id, user_id, role, display_name)
values (
  '10000000-0000-0000-0000-000000000021',
  '00000000-0000-0000-0000-000000000021',
  'facilitator',
  'Owner'
);

insert into public.tickets (id, room_id, issue_key, summary)
values (
  '20000000-0000-0000-0000-000000000021',
  '10000000-0000-0000-0000-000000000021',
  'TT-21',
  'Private ticket'
);

insert into public.votes (room_id, ticket_id, user_id, value)
values (
  '10000000-0000-0000-0000-000000000021',
  '20000000-0000-0000-0000-000000000021',
  '00000000-0000-0000-0000-000000000021',
  '8'
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000022","role":"authenticated","is_anonymous":true}',
  true
);

select is((select count(*) from public.room_members)::bigint, 0::bigint, 'a non-member cannot read the roster');
select is((select count(*) from public.tickets)::bigint, 0::bigint, 'a non-member cannot read tickets');
select is((select count(*) from public.votes)::bigint, 0::bigint, 'a non-member cannot read votes');

select * from finish();
rollback;
