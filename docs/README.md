# Self-hosted documentation

Choose the task you want to complete. Provider walkthroughs include screenshots,
expected results, and recordings; reference guides explain the settings and
operational limits.

## Deploy and maintain the server

| Task | Guide |
| --- | --- |
| Install or upgrade with Docker Compose | [Docker Compose](docker-compose.md) |
| Deploy with Docker Swarm | [Docker Swarm](docker-swarm.md) |
| Deploy to Kubernetes | [Helm chart](../helm/appflowy-cloud/README.md) |
| Back up and restore the instance | [Server backup](BACKUP.md) |
| Investigate administrative and permission changes | [Audit logging](AUDIT.md) |
| Validate deployment configuration in CI | [Deployment CI](deployment-ci.md) |
| Redeem a license invitation | [Invitation code](LICENSE_INVITE_CODE.md) |

## Set up sign-in and automatic provisioning

Start with [Authentication](AUTHENTICATION.md) to choose a sign-in method. SCIM
keeps workspace users and groups synchronized; sign-in is configured separately.

| Task | Guide |
| --- | --- |
| Configure OIDC / OAuth sign-in | [OIDC](OIDC.md) |
| Configure SAML sign-in | [SAML with Okta](OKTA_SAML.md) |
| Sign in against Windows AD or another LDAP directory | [LDAP](LDAP.md) |
| Set up the SCIM endpoint, token, and attribute mappings | [SCIM setup and API reference](SCIM.md) |
| Understand roles, group moves, offboarding, and recovery | [SCIM operations](SCIM_OPERATIONS.md) |

### Choose an illustrated SCIM walkthrough

| Your source directory | Start here | What the media demonstrates |
| --- | --- | --- |
| Microsoft Entra ID | [Entra automatic sync](ENTRA_SCIM_AUTO_SYNC.md) | Real Entra delivery, group lifecycle, user moves, permissions, and seat recovery |
| On-premises Windows Server AD | [AD to SCIM](AD_SCIM_AUTO_SYNC.md) | Connector setup instructions, with separately identified Authentik and Entra downstream evidence; Windows AD import was not recorded |
| Authentik | [Authentik automatic sync](AUTHENTIK_AUTO_SYNC.md) | Group creation, renaming, membership changes, deletion, status, and retry |

Read the provider guide in order for initial setup. For an existing connection,
jump directly to [sync status and recovery](SCIM_OPERATIONS.md#check-sync-status)
or [role and permission mapping](SCIM_OPERATIONS.md#understand-roles-and-permissions).

## Configure application features

| Task | Guide |
| --- | --- |
| Select AI providers and models | [AI model configuration](MODEL_CONFIG.md) |
| Configure search | [Search configuration](SEARCH_CONFIG.md) |
| Connect Google Drive or Google Calendar | [Connections](CONNECTION.md) |
| Find the server API specification | [OpenAPI](OPENAPI.md) |

Use screenshots as visual guidance: labels can differ between releases. The
captions in each walkthrough distinguish real provider delivery, configuration
examples, and automated test evidence.
