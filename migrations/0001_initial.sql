CREATE TABLE IF NOT EXISTS users (
    email varchar(320) PRIMARY KEY,
    name varchar(100) NOT NULL,
    date_of_birth date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public_chats (
    id varchar(36) PRIMARY KEY,
    email varchar(320) NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    title varchar(120) NOT NULL,
    chats jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS public_chats_email_updated_at_idx
    ON public_chats (email, updated_at);
