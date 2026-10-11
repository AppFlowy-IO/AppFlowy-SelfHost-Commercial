# Entra permission and recovery captures

Real Microsoft Entra and AppFlowy test-instance captures from October 9, 2026.
See [the walkthrough](../../ENTRA_SCIM_AUTO_SYNC.md). The original setup and group
lifecycle media remains in `../ad-scim-auto-sync/`.

## Scope and source

The Entra groups are cloud-managed Assigned Security groups. No Windows AD import,
nested-group expansion, or Entra administrator-role mapping is demonstrated.
The AppFlowy demo uses three regular seats: one workspace owner and two active
SCIM users. Charlie is the additional user for the capacity exercise. No paid
license purchase is performed. The system administrator and workspace owner
remain outside the Entra application provisioning scope.

Capture revisions:

- Cloud: `12ad286dc5e6a9103ab701b24c1ad4a411f70295`
- Admin: `92eff4b1138b448b534c93442a9237f4eb7b4af5`
- Web: `523ea9e8ef576f14e3714204a46e54272826ca45`

## Scheduled group move

Bob was added to Quality and removed from Platform in Entra while his direct
enterprise-application assignment remained. The resumed scheduled job delivered
the changes at 11:59 UTC. No on-demand provisioning, restart-provisioning action,
or AppFlowy Retry sync was used for the move. The same cycle updated Bob's SCIM
display name to Bob Demo Scheduled and created Charlie's inactive, seat-waiting
resource. Original SCIM IDs and account identities were compared privately.

Authenticated access checks for Bob changed Platform from Can edit to No access,
Quality from No access to Can edit, and retained Can edit for Shared. The browser
showed the old page denied, the new and shared pages accessible, and the workspace
owner could read Bob's original page at the same URL with unchanged text. The
page was authored by Bob before the move, not merely created by the workspace owner.

## Offboarding and automatic seat recovery

Alice had no direct app assignment and was removed from her final assigned group.
A separately labelled on-demand diagnostic delivered `active:false` at 12:04:32 UTC.
Her SCIM identity remained. Charlie's next pending retry was due at 12:08:38 UTC;
read-only polling observed him active at 12:08:49, with Capacity 1/1 and Synced.
His resource ID was unchanged. No SCIM request for Charlie or Admin Retry sync was
sent between Alice's offboarding and his recovery. A continuous window capture
contains the Waiting for seats → Synced transition. This demonstrates released-seat
recovery, not a purchased-license upgrade.

Charlie was then unassigned and deactivated to free the seat for Alice. Alice's
on-demand reactivation at 12:16:12 UTC retained her SCIM resource ID. A subsequent
manual group diagnostic restored the Quality roster; authenticated access checks
confirmed Alice could edit Quality and Shared again.

## Roles and credential recovery

Entra's app assignment role is User. AppFlowy's workspace role comes from the
connection default and group mappings. Applying Guest to both active demo users
exceeded this instance's one-Guest allowance and reconciliation retried; the
Member default was restored. The completed role-fallback evidence is the isolated
HTTP regression, not a live two-Guest transition.

Token rotation was performed through the Admin connection API. The previous token
returned 401 and the replacement returned 200. Entra's old-credential test showed
Invalid SCIM token. The replacement passed Test connection and Save. Credentials,
the Tenant URL, and request identifiers were excluded from all captures.

## Capture inventory

| File | Evidence |
| --- | --- |
| `32-entra-app-role-assignment.png` | User app role on enterprise-application assignments; Bob remains directly assigned |
| `33-bob-document-before-move.png` | Bob's authored page before the source membership change |
| `34-entra-quality-bob-added.png` | Alice and Bob in Quality after adding Bob |
| `35-entra-remove-old-membership.png` | Only Bob selected for removal from Platform |
| `36-admin-default-role-example.png` | Guest default-role configuration example |
| `37-admin-group-role-mappings-example.png` | Platform Member / Quality Guest configuration example |
| `38-space-permission-policy.png` | Custom space, Can edit for members, No access for everyone else |
| `39-space-group-grant.png` | Platform group as a Space member; roster filtered to the group |
| `40-admin-move-and-seat-waiting.png` | Applied scheduled move and Charlie's Waiting for seats status |
| `41-bob-old-space-revoked.png` | Bob denied his old Platform page after the move |
| `42-bob-new-space-granted.png` | Bob can open the Quality page |
| `43-bob-shared-access-retained.png` | Bob retains Shared access through Quality |
| `44-owner-retains-bob-document.png` | Owner opens the same original Platform document after Bob loses access |
| `45-alice-leaves-provisioning-scope.png` | Alice removed from her final assigned group for the separate offboarding exercise |
| `47-admin-seat-recovered-automatically.png` | Charlie activates without another provider request or manual retry |
| `46-entra-alice-deactivated.png` | Manual on-demand diagnostic successfully changes active True to False |
| `48-entra-alice-reactivated.png` | Manual reactivation changes active False to True on the retained resource |
| `49-entra-revoked-token-error.png` | Error details only: old credential rejected with 401 |
| `50-entra-new-token-success.png` | Entra successfully tests the replacement credential |
| `51-entra-new-token-saved.png` | Replacement credential saved for the provisioning job |
| `entra-group-move.mp4` | 92-second captioned group move, permissions, and original-document retention walkthrough |
| `entra-seat-recovery.mp4` | 85-second captioned offboarding/recovery walkthrough; includes a continuous 45-second automatic status transition |

Each video has a matching plain-text transcript. Both combine real screenshots
with native application-window recordings. Browser bars and account headers are
cropped out, no audio is included, and omitted waiting time is labelled. Captions
distinguish scheduled group delivery, manual offboarding/reactivation diagnostics,
and the automatic AppFlowy seat retry. The role configuration is an example.

The role-mapping images show a configuration example before saving; the Member-only
move used default Member and no mappings. The role-fallback regression independently
asserts Guest → Member → Guest transitions, including an unchanged group's eligibility.

## Privacy

Publish only reviewed browser element captures or cropped application-window video.
Exclude browser bars, tenant/account headers, real email addresses, IDs, public tunnel
addresses, and credentials. Demo users use example.com AppFlowy identities. Portal
columns and UI search filters omit private fields. Accessibility labels used for
element capture do not change visible text or application state. Raw recordings,
traffic, sessions, and credentials stay outside this repository.

The publication check reviewed all 20 new screenshots, decoded all 2,654 video
frames, and OCR-scanned the 748 distinct frames after byte-identical deduplication.
Known tenant/account/credential values and private-domain patterns had no matches
in the new text or media OCR. PNGs contain only image chunks; MP4s contain standard
codec metadata and no audio, location, or creation-time tags. Visual review also
checked the scene transitions, captions, and rendered guide.
