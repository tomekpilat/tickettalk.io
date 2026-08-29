create index room_members_room_last_seen_idx
on public.room_members (room_id, last_seen_at desc);
