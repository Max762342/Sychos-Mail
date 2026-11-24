-- Login-/Account-Datenbank des Sychos Control Panels.
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE IF NOT EXISTS domains (
    id         serial PRIMARY KEY,
    name       citext UNIQUE NOT NULL,
    active     boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mailboxes (
    id            serial PRIMARY KEY,
    email         citext UNIQUE NOT NULL,
    domain_id     integer NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    display_name  text,
    -- 3072 MiB = 3 GiB Speicher pro Postfach
    quota_mb      integer NOT NULL DEFAULT 3072,
    -- Nur fuer die Anzeige / Nachvollziehbarkeit im Panel.
    -- Die eigentliche Mail-Anmeldung prueft Dovecot (SHA512-CRYPT).
    password_hash text,
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mailboxes_domain_idx ON mailboxes (domain_id);

CREATE TABLE IF NOT EXISTS panel_users (
    id            serial PRIMARY KEY,
    email         citext UNIQUE NOT NULL,
    password_hash text NOT NULL,
    is_admin      boolean NOT NULL DEFAULT true,
    last_login_at timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    id         bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    actor      text,
    action     text NOT NULL,
    detail     text
);

INSERT INTO domains (name) VALUES ('sychos.de') ON CONFLICT (name) DO NOTHING;
