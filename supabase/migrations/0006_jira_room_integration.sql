create table public.jira_room_connections (
  room_id uuid primary key references public.rooms(id) on delete cascade,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  site_url text not null check (
    site_url ~ '^https://[a-zA-Z0-9.-]+[.]atlassian[.]net$'
  ),
  email text not null check (char_length(trim(email)) between 3 and 320),
  encrypted_api_token text not null,
  jira_account_id text not null,
  jira_display_name text not null,
  story_points_field_id text,
  story_points_fields jsonb not null default '[]'::jsonb
    check (jsonb_typeof(story_points_fields) = 'array'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.guard_jira_connection_owner()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if not exists (
    select 1 from public.rooms
    where id = new.room_id and owner_id = new.owner_id
  ) then
    raise exception 'Jira connection owner must own the room'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger jira_room_connections_require_owner
before insert or update of room_id, owner_id on public.jira_room_connections
for each row execute function public.guard_jira_connection_owner();

create trigger jira_room_connections_set_updated_at
before update on public.jira_room_connections
for each row execute function public.set_updated_at();

alter table public.jira_room_connections enable row level security;

-- Jira credentials are intentionally unavailable to browser clients. FastAPI uses
-- the service role after independently checking room ownership.
revoke all on public.jira_room_connections from public, anon, authenticated;
grant all on public.jira_room_connections to service_role;

alter table public.tickets
  add column jira_site_url text,
  add column jira_issue_id text,
  add column jira_updated_at timestamptz,
  add column jira_assignee_account_id text,
  add column jira_assignee_display_name text,
  add column final_assignee_account_id text,
  add column final_assignee_display_name text,
  add column jira_writeback_at timestamptz,
  add column jira_writeback_error text;

create unique index tickets_room_jira_issue_unique_idx
on public.tickets (room_id, jira_issue_id)
where jira_issue_id is not null;

create index tickets_room_jira_writeback_idx
on public.tickets (room_id, jira_writeback_at)
where jira_issue_id is not null;
