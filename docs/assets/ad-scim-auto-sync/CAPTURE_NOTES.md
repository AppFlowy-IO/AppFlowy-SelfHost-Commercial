# AD and Entra capture notes

Captured from the real Microsoft Entra admin center and local AppFlowy test
instance on October 9, 2026, for
[the Microsoft Entra guide](../../ENTRA_SCIM_AUTO_SYNC.md).
The media does not establish a Windows AD connection or an ADUC test.

## Earlier setup references

| File | Captured state |
| --- | --- |
| `01-entra-provisioning-overview.png` | Initial provisioning overview in the earlier application |
| `02-entra-credentials.png` | New configuration form with empty endpoint and secret fields |
| `03-entra-group-license-required.png` | Actual group-assignment restriction in the original Free tenant |
| `04-entra-non-gallery-application.png` | Earlier unsubmitted example form, retained as historical media |

These four reference captures did not save provisioning settings or assignments.
The guide now uses the submitted dedicated-application setup below. The original
Free-tenant warning is retained as a troubleshooting reference.

## Dedicated P2 demonstration setup

| File | What to check |
| --- | --- |
| `05-entra-create-application.png` | AppFlowy SCIM Demo and the non-gallery option before Create |
| `06-admin-before-provisioning.png` | Dedicated workspace/connection with zero received groups |
| `07-entra-connection-success.png` | Microsoft reports successful authenticated connection tests |
| `08-entra-create-group.png` | Security group, Assigned membership, and one selected member |
| `09-entra-user-mappings.png` | Supported User mappings and the explicit demo-only example-domain expression |
| `10-entra-group-mappings.png` | Group name, direct members, and stable externalId mappings |
| `11-entra-assign-users-groups.png` | Alice, Bob, Engineering, and Design assigned to the dedicated app |
| `12-entra-assigned-scope.png` | Assigned objects only; out-of-scope deletions enabled |
| `13-entra-two-groups.png` | Two cloud-managed security groups; this is not an AD import |
| `14-entra-initial-member.png` | Engineering starts with Alice as its sole direct member |
| `15-admin-groups-synced.png` | First automatic delivery: two groups, both Synced |
| `16-web-groups-synced.png` | Engineering and the empty Design group in the actual workspace |
| `17-web-alice-member.png` | Engineering's initial AppFlowy roster contains Alice |
| `18-entra-incremental-complete.png` | Entra reports a completed incremental cycle; extracted from the real window recording |
| `19-entra-add-bob.png` | Source renamed to Platform, then Bob added beside Alice |
| `20-entra-remove-alice.png` | Source membership is Bob only after removing Alice |
| `21-entra-delete-design.png` | Only the disposable Design group selected for deletion |
| `22-entra-create-quality.png` | New Quality group with one selected direct member |
| `23-entra-updated-assignments.png` | Quality assigned; Platform and both independent users retained |
| `24-entra-user-display-name.png` | Bob's display-name edit before Save; property search excludes private fields |
| `25-admin-updated-groups.png` | Platform and Quality reach Synced after automatic delivery |
| `26-web-updated-groups.png` | Final group list: Design absent, Quality present, Engineering renamed |
| `27-web-platform-bob.png` | Same original group now contains Bob instead of Alice |
| `28-web-quality-alice.png` | Newly provisioned Quality contains Alice |
| `29-entra-user-update-result.png` | Successful displayName modification from the separate manual user diagnostic |

The isolated AppFlowy instance uses a three-seat commercial test license: one
existing owner and two provisionable users. It is built with self-hosted behavior
and local commercial test support. The owner and system administrator are excluded
from the Entra provisioning scope. The P2 tenant has licenses assigned to its
administrator and the two demo users; Microsoft licensing is separate from the
AppFlowy seat limit.

The demo uses an ephemeral HTTPS tunnel to a local proxy restricted to the SCIM
routes and the dedicated bearer token. Public media uses an example URL and never
contains the real tunnel hostname or token. The User mapping deliberately creates
example.com identities; this is documented as a demo-only transformation.

Source revisions used for capture:

- Cloud: `12ad286dc5e6a9103ab701b24c1ad4a411f70295`
- Admin: `92eff4b1138b448b534c93442a9237f4eb7b4af5`
- Web: `523ea9e8ef576f14e3714204a46e54272826ca45`

## Recorded delivery and verification

Provisioning was started at 07:30 UTC. The first scheduled group delivery completed
at 07:50 UTC, and an incremental cycle delivered the group edits at 08:02 UTC.
The portal displayed a 40-minute configured interval; these observed timings are
not a delivery guarantee. All times in this paragraph are UTC; screenshots use
the workstation's UTC+8 display.

The initial group creation, rename, member addition/removal, creation of Quality,
and deletion of Design used the active Entra provisioning job. No on-demand group
provisioning, restart-provisioning action, or AppFlowy Retry sync was used. A
separate on-demand Alice user check ran during setup and is disclosed in the guide.
The later Bob display-name example uses a separate, explicitly labeled on-demand
user diagnostic. It is not evidence of scheduled user-attribute delivery.
The SCIM readback confirmed Bob Demo Updated; the existing personal profile and
workspace roster still used the same example-domain email.

Read-only API comparisons confirmed that Platform retained Engineering's group
identity, Design was absent, Platform contained exactly Bob, and Quality contained
exactly Alice. Both final groups reported Synced. HTTP evidence confirmed group
creation (201), membership/name updates (200), and deletion (204). Raw payloads
and private identifiers are deliberately excluded from the repository.

The source briefly contained both Alice and Bob between edits. Those edits were
made before the next cycle, so the guide does not claim that AppFlowy displayed
every intermediate source state. User offboarding and the Windows AD import stage
are additional procedures, not outcomes proved by this Entra recording.

`entra-auto-sync.mp4` is a silent, captioned walkthrough combining real setup/source
screenshots with window recordings of starting provisioning and the AppFlowy
status panels. Waiting time and unrelated navigation are omitted. The accompanying
`entra-auto-sync-transcript.txt` provides the same captions and timing.

## Privacy and capture method

Images are browser element captures or a cropped frame from the window recording.
They exclude account headers, tenant names
and domains, object/workspace identifiers, real email addresses, browser address
bars, and credentials. Portal column selection was used to omit identifier/email
columns. Interface labels and result values were not replaced or generated.
Accessibility attributes were adjusted only to expose existing iframe/panel
content to the capture tool; this did not change visible interface content.

All 29 PNGs were visually inspected, OCR-scanned for private identifiers and
credentials, and checked for embedded text/EXIF chunks. No matches or metadata
chunks were found. Every frame of each live video segment was extracted for OCR;
only byte-identical duplicate PNGs shared an OCR result. Static source images and
captions were also reviewed. The output video has no audio track or private metadata.
Raw screenshots, credentials, traffic logs, and recordings
remain outside the repository. Only reviewed media belongs in this directory.
