CREATE SCHEMA IF NOT EXISTS qa_data;

CREATE TABLE IF NOT EXISTS qa_data.users (
    id varchar(36) PRIMARY KEY,
    username varchar(32) NOT NULL UNIQUE,
    email varchar(320) NOT NULL UNIQUE,
    password_hash varchar(255) NOT NULL,
    role varchar(20) NOT NULL DEFAULT 'QA_MANAGER'
        CHECK (role IN ('ADMIN', 'QA_MANAGER', 'DEVELOPER', 'VIEWER')),
    created_at timestamptz NOT NULL DEFAULT now()
);
