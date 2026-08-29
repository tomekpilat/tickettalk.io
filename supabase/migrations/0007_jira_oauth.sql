alter table public.jira_room_connections
  alter column email drop not null,
  alter column encrypted_api_token drop not null,
  add column auth_method text not null default 'api_token'
    check (auth_method in ('oauth', 'api_token')),
  add column cloud_id text,
  add column encrypted_access_token text,
  add column encrypted_refresh_token text,
  add column token_expires_at timestamptz;

alter table public.jira_room_connections
  add constraint jira_room_connections_credentials_check check (
    (
      auth_method = 'api_token'
      and email is not null
      and encrypted_api_token is not null
      and cloud_id is null
      and encrypted_access_token is null
      and encrypted_refresh_token is null
      and token_expires_at is null
    )
    or
    (
      auth_method = 'oauth'
      and email is null
      and encrypted_api_token is null
      and cloud_id is not null
      and encrypted_access_token is not null
      and encrypted_refresh_token is not null
      and token_expires_at is not null
    )
  );

comment on column public.jira_room_connections.auth_method is
  'OAuth is the normal connection path; api_token is an advanced fallback.';
