"""Introduce reusable tenant-owned knowledge bases.

Revision ID: 0002_knowledge_bases
Revises: 0001_existing_schema
"""
from alembic import op

revision = "0002_knowledge_bases"
down_revision = "0001_existing_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        create table knowledge_base (
          id text primary key,
          user_id uuid not null references auth.users(id) on delete cascade,
          name text not null check (btrim(name) <> ''),
          description text not null default '',
          status text not null default 'active' check (status in ('active', 'archived')),
          legacy_agent_id text references agent(id) on delete set null,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          unique (id, user_id)
        );

        create index idx_knowledge_base_user_status
          on knowledge_base(user_id, status);
        create unique index uq_knowledge_base_active_name
          on knowledge_base(user_id, lower(name)) where status = 'active';
        create unique index uq_knowledge_base_legacy_agent
          on knowledge_base(user_id, legacy_agent_id) where legacy_agent_id is not null;

        alter table content_item add column knowledge_base_id text;

        with referenced_agents as (
          select a.id, a.user_id, a.name,
                 row_number() over (
                   partition by a.user_id, lower(btrim(a.name) || ' Knowledge')
                   order by a.id
                 ) as duplicate_number
          from agent a
          where exists (
            select 1 from content_item c
            where c.agent_id = a.id and c.user_id = a.user_id
          )
        )
        insert into knowledge_base (
          id, user_id, name, description, status, legacy_agent_id, created_at, updated_at
        )
        select gen_random_uuid()::text,
               user_id,
               case when duplicate_number = 1
                    then btrim(name) || ' Knowledge'
                    else btrim(name) || ' Knowledge (' || left(id, 8) || ')'
               end,
               'Migrated from existing agent content.',
               'active', id, now(), now()
        from referenced_agents;

        insert into knowledge_base (
          id, user_id, name, description, status, created_at, updated_at
        )
        select gen_random_uuid()::text, orphan.user_id, 'Recovered Content',
               'Documents whose original agent no longer exists.', 'active', now(), now()
        from (
          select distinct c.user_id
          from content_item c
          where not exists (
            select 1 from agent a where a.id = c.agent_id and a.user_id = c.user_id
          )
        ) orphan;

        update content_item c
        set knowledge_base_id = kb.id
        from knowledge_base kb
        where kb.user_id = c.user_id and kb.legacy_agent_id = c.agent_id;

        update content_item c
        set knowledge_base_id = kb.id
        from knowledge_base kb
        where c.knowledge_base_id is null
          and kb.user_id = c.user_id
          and kb.name = 'Recovered Content'
          and kb.legacy_agent_id is null;

        do $$
        begin
          if exists (select 1 from content_item where knowledge_base_id is null) then
            raise exception 'knowledge-base backfill left content unassigned';
          end if;
        end $$;

        alter table content_item alter column knowledge_base_id set not null;
        alter table content_item alter column agent_id drop not null;
        alter table content_item add constraint fk_content_knowledge_tenant
          foreign key (knowledge_base_id, user_id)
          references knowledge_base(id, user_id);
        create index idx_content_item_knowledge_base
          on content_item(knowledge_base_id);
        create index idx_content_item_user_knowledge_base
          on content_item(user_id, knowledge_base_id);

        alter table knowledge_base enable row level security;
        create policy "owner_only" on knowledge_base for all
          using (auth.uid() = user_id)
          with check (auth.uid() = user_id);
    """)


def downgrade() -> None:
    raise RuntimeError("Knowledge-base ownership migration is intentionally irreversible")
