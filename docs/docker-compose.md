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

If upgrading an installation previously started from `docker/`, move its existing `.env` to the repository root and retain its Compose project name. For the old default, add `COMPOSE_PROJECT_NAME=docker` to `.env`; if you used a custom project name, keep that value. This reuses the existing containers, networks, and data volumes.
