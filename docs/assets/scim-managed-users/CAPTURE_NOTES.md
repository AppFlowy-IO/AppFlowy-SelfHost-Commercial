# Managed-user configuration screenshots

These are captures of the implemented AppFlowy Admin UI with synthetic Cypress
API fixtures. They illustrate the controls and saved summary, not live Entra
provisioning or server reconciliation.

| File | What it shows |
| --- | --- |
| `01-managed-user-settings.png` | The managed-user section of Edit SCIM Connection, with workspace profile-name sync and direct SCIM roles enabled |
| `02-managed-user-summary.png` | The connection's saved policy summary |
| `03-edit-connection-action.png` | The SCIM Provisioning page and connection Actions menu, showing where to open Edit connection |
| `04-connection-form-context.png` | The entire edit form, including the default role, group mapping, managed-user controls, and Save changes action |

Source: `apps/super/cypress/e2e/admin/scim-mocked-api.cy.ts` in AppFlowy-Admin,
test **saves managed-user policies with explicit role precedence and preserves
them on reopen**, with `SCIM_DOC_SCREENSHOTS=true`.

The capture runs entirely against mocked API responses and mock authentication.
The source fixture uses an example workspace and invented identifiers. The
context captures show these synthetic values and a nonfunctional localhost
endpoint; production uses its own HTTPS endpoint. There are no real account names,
emails, tenant domains, identifiers, tokens, browser chrome, or operating-system
details. All four images were visually checked. Their PNG chunks contain only
`IHDR`, `IDAT`, and `IEND`, with no embedded text or location metadata. No
AI-generated content or retouched UI is used.

The context images use headless Chrome with a browser surface large enough for
the capture viewport. Browser display size and Cypress viewport size are
separate settings; see [Cypress's browser launch documentation](https://docs.cypress.io/api/node-events/browser-launch-api).
The repository's optional `SCIM_DOC_SCREENSHOTS` mode configures that surface
without changing ordinary test runs.

Existing Entra and Authentik recordings remain in their original asset folders.
Their captions describe the behavior and configuration at capture time; they do
not demonstrate the new optional profile-name or direct-role policies.
