# SIEM guide capture notes

Captured on November 25, 2026 for [Send audit logs to a SIEM](../../SIEM.md) from a production
build of the Admin console's **Developer settings** page, in the light theme at 1280 × 720.
The page ran against scripted server responses, so the token names, IDs, workspace, and events
are examples. The token itself stays masked, as it is in the real dialog.

| File | What to check |
| --- | --- |
| `01-developer-settings.png` | **Settings → Developer settings** with the **Create token** button |
| `02-create-token.png` | Name, **One workspace** with a workspace selected, and **Read audit logs** checked |
| `03-save-token.png` | The one-time token with **Copy token**, **Test connection**, and **Copy command** |
| `04-test-connection.png` | Both test requests answered with HTTP 200 and one event each |
| `05-token-list.png` | A workspace token and an installation token with **Rotate** and **Revoke** |
