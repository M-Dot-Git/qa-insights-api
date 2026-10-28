-- Create Keycloak database and user
-- PostgreSQL automatically creates the POSTGRES_USER/POSTGRES_DB, but Keycloak
-- needs its own dedicated database and user.

CREATE USER keycloak WITH PASSWORD 'keycloak_password';
CREATE DATABASE keycloak OWNER keycloak;
GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak;