-- Provider connections for encrypted, reusable model credentials.
create table provider_connection (
  id                 text primary key,
  user_id            uuid not null references auth.users(id) on delete cascade,
  provider           text not null check (provider in ('gemini', 'groq', 'openrouter', 'openai', 'anthropic')),
  display_name       text not null,
  secret_ref         text not null,
  validation_status  text not null default 'unverified' check (validation_status in ('valid', 'invalid', 'unverified')),
  last_validated_at  text,
  created_at         text not null,
  unique (user_id, display_name),
  foreign key (user_id, secret_ref) references user_secret(user_id, name) on delete cascade
);
create index idx_provider_connection_user_id on provider_connection(user_id);

alter table provider_connection enable row level security;
create policy "owner_only" on provider_connection using (auth.uid() = user_id);
