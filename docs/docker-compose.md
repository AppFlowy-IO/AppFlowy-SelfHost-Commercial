# Docker Compose

With Docker and the Docker Compose plugin installed, first copy the environment template from the repository root:

```bash
cp deploy.env .env
```

Edit `.env` to set your domain, HTTPS/WebSocket schemes, credentials, and optional email or AI settings. Replace the example passwords and JWT secret before exposing the deployment publicly. Compose [loads the root `.env` automatically](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), and Git ignores this file.

Compose uses the public `appflowyinc/appflowy_cloud` and `appflowyinc/appflowy_worker` images. Both provide AMD64 and ARM64 builds, and Docker selects the image architecture for your host automatically.

Nginx configuration and certificates remain in [`docker/nginx`](../docker/nginx). For HTTPS, replace the bundled development certificate and key in `docker/nginx/ssl/` with your deployment's certificates.

Then start the services from the repository root:

```bash
docker compose up -d
```

With the default localhost settings, open [AppFlowy Web](http://localhost) or the [Admin console](http://localhost/console). The template creates the admin account `admin@example.com` with password `password`.

If upgrading an installation previously started from `docker/`, move its existing `.env` to the repository root and retain its Compose project name. For the old default, add `COMPOSE_PROJECT_NAME=docker` to `.env`; if you used a custom project name, keep that value. This reuses the existing data volumes and the default network. Containers whose definition changed are recreated in place: `nginx` and `appflowy_cloud` leave the old `cloud_proxy` network, and `minio`, `appflowy_cloud`, and `appflowy_worker` move to new image references; the other containers are reused. The old `<project>_cloud_proxy` network is left behind and can be removed with `docker network rm` after the upgrade.

## OAuth providers

The [`gotrue` service](../docker-compose.yml) forwards Google, GitHub, and Discord OAuth settings from the root `.env`. The settings are listed in [`deploy.env`](../deploy.env).

For provider setup instructions, see the [authentication guide](AUTHENTICATION.md).

Set `FQDN` and `SCHEME` for your public deployment URL before configuring a provider. Register an OAuth application with that provider and set its callback URL to `${API_EXTERNAL_URL}/callback`, which resolves to `https://your-domain/gotrue/callback` for an HTTPS deployment.

Update the matching provider settings in `.env`. For example, for Google:

```dotenv
GOTRUE_EXTERNAL_GOOGLE_ENABLED=true
GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID=your-client-id
GOTRUE_EXTERNAL_GOOGLE_SECRET=your-client-secret
GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI=${API_EXTERNAL_URL}/callback
```

For GitHub or Discord, use the corresponding `GOTRUE_EXTERNAL_GITHUB_*` or `GOTRUE_EXTERNAL_DISCORD_*` settings. Leave providers you do not use disabled.

Apply the updated environment from the repository root:

```bash
docker compose up -d gotrue
```

## SAML

For Okta, follow the [SAML setup guide](OKTA_SAML.md). The SAML settings forwarded to GoTrue are `GOTRUE_SAML_ENABLED` and `GOTRUE_SAML_PRIVATE_KEY`; configure them in the root `.env`.

## Enterprise identity

SCIM provisioning, custom OIDC / OAuth providers, and LDAP sign-in are configured in the Admin console rather than through `.env`. See [SCIM Provisioning](SCIM.md), [OIDC / OAuth](OIDC.md), and [LDAP](LDAP.md). The bundled [`docker/nginx/nginx.conf`](../docker/nginx/nginx.conf) already routes `/scim` to AppFlowy Cloud and sets `X-Forwarded-For` for `/api`; if you use a customized Nginx configuration, the SCIM and LDAP guides show the exact directives to add.
