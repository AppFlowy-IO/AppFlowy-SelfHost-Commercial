# Expanded SCIM demo: evidence and limitations

[Eight-person walkthrough](../../SCIM_DEMO.md) · [October 11 record](../scim-demo/CAPTURE_NOTES.md)

The **October 12, 2026** run verified eight separate people, nine workspace group
projections and a group move with restoration. The opening assignments were
restored, the same accounts remained active, and AppFlowy used **9 of 10 seats**.

## Verified results

| Phase | Observed result |
| --- | --- |
| Directory setup | Eight ordinary Entra users, each licensed with P2 and assigned to one source group |
| Workspace provisioning | Six Demo groups, two HR groups and one Executive group; each had the intended single eligible member |
| Workspace roles | Dana is Demo Owner; all other assigned memberships are Member; none of the test people is an instance administrator |
| Web baseline | 72 unique person/space checks passed: 13 Edit, 23 View, 36 No access |
| Saved baseline content | All 13 editor notes saved; all 23 attempted viewer notes absent from independently read saved content |
| API baseline | All 72 access cells and 107 supporting assertions passed, including exact identities, roles, rosters, grants and positive owner controls |
| Charlie moved to HR | Nine fresh Web checks passed: one Edit, four View, four No access; account and original notes retained |
| Charlie restored to Super_Users | Nine fresh Web checks passed: two Edit, three View, four No access; HR note retained after losing Edit there |
| Final state | Nine group rosters restored to their single baseline member; final 72-cell API and saved-marker verification passed |

The 72 baseline cases are nine document targets for each of eight people. They
are not a claim about every page, database operation or creation action. The
additional moved/restored phases contribute 18 separate Web checks. Browser
interactions and independent read-only API checks were recorded separately.

Demo's baseline arrived through normal provisioning after it was started. HR and
Executive baseline membership used **Provision on demand**. Charlie's move and
restoration also used on-demand delivery; this run does not claim a new scheduled
member-move timing test. The October 11 record contains that separate evidence.

## Build and session provenance

| Component | Recorded setup |
| --- | --- |
| Cloud, Worker, Search | Clean source revision `336ce8147175e93cc0a7c369d5f2b46a9ae34494`; each service built with its own `self-host-af` feature |
| License policy | Normal self-hosted build; neither `commercial-local-test` nor `commercial-ci` enabled |
| Web | Isolated checkout at `df5c65699fd408e1f0522fbe16a35943fefe6f35`, served locally for all counted Web checks |
| Admin | Existing local development build with group-role mappings, sync monitoring and retry controls |
| Database | Retained demo data; 281 successful migrations and no checksum mismatches; no reset |
| Identity | Genuine ordinary sessions for the existing SCIM-provisioned identities, with the setup owner separate |

This validates a **local source build**, not a published Docker release. It does
not test Entra SSO or the interactive sign-in flow. Microsoft P2 assignments and
AppFlowy's licensed seat capacity were verified separately. Activation happened
before expanded provisioning; it is not proof of retrying a user previously
blocked by the three-seat limit.

Preliminary checks on a concurrently edited Web checkout are excluded from the
counted baseline. All 72 counted cases were repeated on the isolated revision.

## Charlie's move and retained content

Charlie was added to HR and that addition was verified before Super_Users was
removed. HR retained his Demo application assignment, so temporary Users
membership was unnecessary. AppFlowy then showed HR with two members and
Super_Users with zero. The same Cloud, GoTrue and SCIM identities, active
workspace membership and occupied seat count were retained.

General and Demo Intelligence changed from Edit to View; Demo's HR space changed
from View to Edit. Other access boundaries were unchanged. Independent reads
confirmed all original paragraphs remained and Charlie's new HR sentence saved.
After restoration, that HR note remained and the other eight document hashes
were unchanged from before the move.

An old General editor could still display forbidden local input after revocation,
even after a tab reload. A fresh isolated session was read-only and did not show
that text. Repeated canonical reads found all six stale/fresh-viewer test markers
absent from all nine notes. The old page was closed before restoring Edit.
These reads included pending accepted realtime updates, not only an older
PostgreSQL snapshot. No specific HTTP rejection or matching denial log is claimed.

One intermediate hash-only check failed because the authorized HR edit arrived
while the checker still expected pre-edit hashes. Its forbidden-marker checks
remained clear. The subsequent post-HR check passed with the correct expectation:
the HR edit saved, other hashes stayed unchanged and original paragraphs remained.

## Screenshot index

All 26 PNGs were reviewed visually and checked for PNG integrity. No account
emails, identifying domains, tenant/object identifiers, credentials or customer
name are visible. No text/EXIF metadata is present. These are genuine UI captures;
no pixels or visible status values were rewritten. No video was recorded.

| Image | What it establishes |
| --- | --- |
| [01](01-entra-eight-groups.png) | Entra lists eight assigned security groups; membership is checked separately |
| [02](02-eight-licensed-demo-users.png) | Eight Demo-filtered users have Microsoft Entra ID P2; this does not establish AppFlowy access |
| [03](03-entra-demo-workspace-assignments.png) | The Demo application has six intended groups assigned |
| [04](04-entra-hr-workspace-assignments.png) | The HR application has W_RH_view and W_RH_edit assigned |
| [05](05-entra-executive-workspace-assignments.png) | The Executive application has Codir assigned |
| [06](06-admin-demo-six-groups-synced.png) | Demo's six received groups each show one eligible member and Synced |
| [07](07-admin-hr-two-groups-synced.png) | HR has two Synced groups with one eligible member each |
| [08](08-admin-executive-group-synced.png) | Executive has one Synced Codir group with one eligible member |
| [09](09-admin-owner-role-mapping.png) | The Demo connection maps the Admin group to workspace Owner; this does not grant instance administration |
| [10](10-web-alice-general-view.png) | Alice opens General Notes in Demo; read-only behavior and unchanged saved content were checked separately |
| [11](11-web-bob-hr-view.png) | Bob opens General Notes in HR Workspace; the same separate View checks passed |
| [12](12-web-bob-demo-denied.png) | Bob's direct link into Demo displays No access to this page |
| [13](13-web-charlie-editor.png) | Charlie's saved edit in Demo Intelligence; Super_Users access was verified |
| [14](14-web-farah-hr-space-editor.png) | Farah's saved edit in the HR space inside Demo Workspace |
| [15](15-web-hugo-product-editor.png) | Hugo's saved edit in Demo's Product space |
| [16](16-web-grace-hr-workspace-editor.png) | Grace's saved edit in HR Workspace's Shared space |
| [17](17-web-eve-executive-editor.png) | Eve's saved edit in Executive Committee Workspace's Shared space |
| [18](18-web-dana-admin-editor.png) | Dana's saved edit in Demo's Internal IT space; does not by itself prove administration |
| [19](19-web-custom-space-permissions.png) | General is Custom: Space members Can edit; everyone else in Demo Can view |
| [20](20-web-super-users-space-grant.png) | Super_Users is an ordinary Space member; its Edit level comes from the policy |
| [21](21-entra-charlie-added-to-hr.png) | Source HR contains Charlie and Farah after Charlie's addition |
| [22](22-entra-charlie-removed-from-super-users.png) | Source Super_Users is empty after Charlie's removal |
| [23](23-admin-charlie-move-synced.png) | Received HR has two eligible members and Super_Users zero, both Synced |
| [24](24-web-charlie-after-move-view.png) | Charlie can still read Demo Intelligence with his original note retained; View enforcement checked separately |
| [25](25-web-charlie-after-move-hr-edit.png) | Charlie's authorized HR note is visible after the move; canonical persistence checked independently |
| [26](26-admin-baseline-restored.png) | Demo groups restored to one eligible baseline member each |

Images 10–18 are from the isolated Web run. Older Alice/Bob paragraphs remain in
the documents as history; use the opening person/group table for current access.
The separate interaction and saved-content evidence establishes enforcement;
page text and screenshots alone do not prove edit permission. A Synced badge
proves applied received data, not delivery of every newer directory change.

## Limits and cleanup

- Ordinary Space members share one permission level. The demonstrated recipe
  permits other admitted workspace members to View; it cannot give independent
  ordinary groups View/Edit while denying everyone else.
- Selected-person/group creation controls, future-space grants and overriding
  denies are outside the supported configuration demonstrated here.
- Workspace Owner does not bypass Private-space access or automatically rewrite
  explicit Custom-space ownership when promoted or demoted.
- Stale editors do not immediately refresh after revocation, as described above.
- AD import, nested groups, database mutations, creation actions, license-retry
  recovery and Entra SSO were not tested by this run.
- Group creation/rename/deletion, workspace offboarding and administrator demotion
  were not repeated with the eight fixed personas. See the dated October 11 record.

The baseline is restored. All three Entra provisioning jobs were paused, the
three demo SCIM connections were disabled, and the temporary tunnel and proxy
were stopped. Before/after checks confirmed that only the connections' enabled
flags changed: users, groups, memberships and roles were retained for local
inspection. To run the example again, restore a reachable endpoint, enable the
connections and resume provisioning.

Trial cancellation remains an action for the account owner. Raw diagnostics,
session credentials and private identifiers remain outside the repository.
