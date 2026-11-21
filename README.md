# Dockerized IMAP server

A small Postfix (SMTP) and Dovecot (IMAP) server for local development and
mail-flow debugging. It provides a catch-all mailbox so messages sent to
arbitrary recipient addresses can be inspected locally. An optional regular
mailbox can also be configured.

> **Development use only.** This image uses a fixed debug password, a
> development TLS certificate, and unauthenticated SMTP. Do not expose it to an
> untrusted network or use it for production mail.

## Quick start

Copy the example Compose file and adjust the mailbox settings if needed:

```sh
cp docker-compose.yml.dist docker-compose.yml
# Edit MAILNAME, MAIL_ADDRESS, and MAIL_PASS in docker-compose.yml.
docker compose up --build
```

Compose builds the image from this checkout, publishes ports only on the host's
loopback interface, and stores messages in a named volume. To stop the services
while keeping mail, run `docker compose down`. To delete the mail volume too,
run `docker compose down -v`.

### Configuration

- `MAILNAME`: mailbox domain; the image default is `localdomain.test`.
- `MAIL_ADDRESS`: optional simple `local-part@domain` mailbox address.
- `MAIL_PASS`: password for `MAIL_ADDRESS`; required when that address is set.

The example Compose file includes sample values for local use. Change the
password before use, and don't reuse it for any real account.

## Connect to the server

From a mail client or application running on the **host**, use `localhost`:

| Service | Host | Port | Security / authentication |
| --- | --- | ---: | --- |
| SMTP | `localhost` | `2525` | No TLS or authentication; recipients are redirected to the debug mailbox. |
| IMAP | `localhost` | `9930` | IMAPS. The bundled development certificate is self-signed. |
| IMAP (optional) | `localhost` | `1430` | IMAP with STARTTLS; TLS is required. |

The Compose port mappings bind to `127.0.0.1`. If you change them, keep the
service on a trusted, local-only network. In particular, never publish the
unauthenticated SMTP port to the public internet.

From another container attached to the same Compose network, use the service
name `imap` and the container ports: SMTP `25`, IMAPS `993`, or IMAP with
STARTTLS `143`.

### Catch-all debug mailbox

SMTP recipients are redirected to `debug@${MAILNAME}`, except mail addressed
to the configured `MAIL_ADDRESS`. Use these credentials to inspect catch-all
messages:

- **Username:** `debug@example.org` (replace the domain with `MAILNAME`)
- **Password:** `debug`

The SMTP server does not require authentication. This is deliberate for local
mail-flow testing, not a safe production configuration. The self-signed IMAP
certificate will trigger a trust warning in many clients; trust it only in a
local development setup, or temporarily disable certificate verification for
that test account.

### Optional normal mailbox

When `MAIL_ADDRESS` and `MAIL_PASS` are set, the image creates a mailbox for
that account. Messages addressed to it are delivered there rather than to the
catch-all. For example, the sample settings create `address@example.org` with
the configured `MAIL_PASS`.

## Tests

The dependency-free smoke tests build and exercise the Docker image. Docker must
be installed and running:

```sh
python3 -m unittest discover -s tests -v
```

The local test command builds a fresh, uniquely tagged image by default. To
reuse an image built separately, set both `IMAGE` and `REUSE_IMAGE=1`.
