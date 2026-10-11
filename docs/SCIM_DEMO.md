# SCIM group synchronization and permissions: a complete example

[Documentation](README.md) / [SCIM setup](SCIM.md) / [Entra setup](ENTRA_SCIM_AUTO_SYNC.md)

This guide shows how a change in Microsoft Entra ID reaches AppFlowy and changes
what a person can access. It uses eight groups, three workspaces, and two test users.

| Where | What you configure |
| --- | --- |
| Microsoft Entra ID | Users, groups, and group membership |
| AppFlowy Admin | The workspace that receives each group and its workspace role |
| AppFlowy Web | The spaces that each group can view or edit |

After setup, SCIM keeps group names and membership in sync. Moving someone between
groups changes their access without deleting their account or saved content.

**Some requested permissions still need implementation.** Check the
[current limitations](#what-remains-unsupported) before using this configuration.
Click any screenshot to view it at full size; expand the supporting screenshots
when you need more detail.

## In this guide

- [Permission matrix](#the-permission-matrix)
- [Current limitations](#what-remains-unsupported)
- [1. Prepare workspaces and test users](#1-prepare-three-workspaces-and-two-test-users)
- [2. Create the AppFlowy connections](#2-create-one-appflowy-scim-connection-per-workspace)
- [3. Create and assign the Entra groups](#3-create-and-assign-the-eight-entra-groups)
- [4. Check mappings and start provisioning](#4-check-mappings-and-start-provisioning)
- [5. Check synced groups](#5-confirm-the-received-groups-in-appflowy-admin)
- [6. Set space permissions](#6-configure-content-access-in-appflowy-web)
- [7. Test viewer and editor access](#7-verify-the-matrix-as-alice-and-bob)
- [8. Move people between groups](#8-move-a-member-without-deleting-the-user)
  - [Change Bob between HR viewer and editor](#bobs-hr-editor-and-restored-viewer-phases)
- [9. Remove workspace access or an Admin role](#9-test-workspace-offboarding-and-administrator-demotion)
- [10. Create, rename and delete a group](#10-test-group-creation-rename-and-deletion)
- [Verified results](#verified-results)
- [Finish the demo](#finish-the-temporary-demo)

## The permission matrix

### Groups and their purpose

| Group name | Details |
| --- | --- |
| `Admin` | Admin |
| `Users` | Every new Demo employee is automatically added to the Users group |
| `Super_Users` | One champion per team with specific Edit rights (notably on databases) |
| `Codir` | Executive Committee (CODIR) managers group |
| `HR` | Business team group for the HR team |
| `W_RH_view` | Individual with View access to the team's dedicated confidential workspace |
| `W_RH_edit` | Individual with Edit access to the team's dedicated confidential workspace |
| `Product` | Business team group for the Product team |

`Users` is a regular group in AD or Entra ID. In this example, its members receive
access to Demo Workspace. Add people manually or through a directory rule; the
group's name and description do not add anyone automatically.

For someone who should access only HR Workspace, use `W_RH_view` or `W_RH_edit`.
Keep them out of `Users` and other Demo Workspace assignments. Membership in both
grants access to both workspaces.

### Requested content and administration permissions

| Group | Admin | DEMO WORKSPACE | General | Demo Intelligence | Internal IT | HR | Product | HR WORKSPACE | EXECUTIVE COMMITTEE WORKSPACE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Admin | Edit | Edit | Edit | Edit | Edit | Edit | Edit | No Access | No Access |
| Users | No Access | View | View | View | View | View | View | No Access | No Access |
| Super_Users | No Access | View | Edit | Edit | View | View | View | No Access | No Access |
| Codir | No Access | View | View | View | View | View | View | No Access | Edit |
| HR | No Access | View | View | View | View | Edit | View | No Access | No Access |
| W_RH_view | No Access | No Access | No Access | No Access | No Access | No Access | No Access | View | No Access |
| W_RH_edit | No Access | No Access | No Access | No Access | No Access | No Access | No Access | Edit | No Access |
| Product | No Access | View | View | View | View | View | Edit | No Access | No Access |

Read the table as follows:

- **Admin** means administration of Demo Workspace, not the instance Admin frontend.
- **HR** is a space inside Demo Workspace. **HR WORKSPACE** is a separate workspace.
- **View/Edit** describes content access. Most people remain workspace **Members**.
- Here, **No Access** means this group grants no access. Another group or direct
  invitation can still grant it. If you need a rule that overrides other grants,
  that requires a separate deny feature.

### Requested creation rules

These are the requested rules, not a list of completed features. The current UI
cannot fully enforce them; see the limitations below.

<details>
<summary>Show the requested creation rules for each group</summary>

| Group | Creation rule |
| --- | --- |
| Admin | With Edit rights, users can create workspaces, spaces and pages |
| Users | With Edit rights, users can create pages but not spaces |
| Super_Users | With Edit rights, users can create pages but not spaces |
| Codir | With Edit rights, users can create pages but not spaces |
| HR | With Edit rights, users can create pages but not spaces |
| W_RH_view | With Edit rights, users can create pages but not spaces |
| W_RH_edit | With Edit rights, users can create spaces and pages |
| Product | With Edit rights, users can create pages but not spaces |

</details>

Editing an existing page, creating a page, creating a space, and creating a whole
workspace are separate permissions. A View-only user does not gain creation rights
from the wording “With Edit rights.” Whole-workspace creation should be limited
to selected people; this is separate from membership in the `Admin` group.

## What remains unsupported

| Requirement | Current behavior |
| --- | --- |
| Editor groups edit; other workspace members view | Supported by the Custom-space setup in this guide |
| Give different groups View/Edit while denying everyone else | Ordinary Space members share one permission level; independent group levels need implementation |
| Edit pages but prevent space creation | The backend has a workspace policy, but its controls are missing from the inspected clients |
| Only selected members or groups create spaces | Needs implementation |
| Only selected people create workspaces | Needs implementation |
| Automatically grant access to every future space | Not provided by the explicit space grants used here |
| Immediately refresh access in an already-open page | The page can keep old content and allow local typing; fresh sessions enforce the new access |

In this demo, all three workspaces allowed **Members and Owners** to create spaces.
Do not treat this setup as enforcing “edit but cannot create spaces.”

After access was reduced, test text typed in an old browser tab did **not** save
to the server. This is still a client limitation: the old page did not immediately
clear or become read-only.

## 1. Prepare three workspaces and two test users

Use a test installation with three available seats: a setup owner, **Alice Demo**,
and **Bob Demo**. Keep the setup owner outside SCIM and use Alice and Bob for the
permission tests.

| Workspace | Spaces used in this example | Purpose |
| --- | --- | --- |
| Demo Workspace | General, Demo Intelligence, Internal IT, HR, Product | Shared company content |
| HR Workspace | General and Shared | Confidential team content |
| Executive Committee Workspace | General and Shared | Executive content |

The two spaces named **Shared** belong to different workspaces. They are test
spaces used to check HR and Executive Committee access.

Before continuing:

1. Check the [Entra license and network requirements](ENTRA_SCIM_AUTO_SYNC.md#step-1-check-the-license-and-network-requirements).
2. Configure [sign-in](AUTHENTICATION.md). SCIM manages accounts and membership;
   it does not sign people in. Their SCIM email must match their AppFlowy login.
3. Create a test page in each space. Confirm the setup owner can open every page.
4. Use separate Web sessions for the owner, Alice, and Bob.

This demo uses groups managed in Entra. For on-premises Windows AD, configure
and verify the [AD connector](AD_SCIM_AUTO_SYNC.md) first. AD import and nested
groups were not tested here. Existing memberships outside these three workspaces
must be reviewed separately.

## 2. Create one AppFlowy SCIM connection per workspace

In AppFlowy Admin, open **Authentication → SCIM Provisioning** and
[create a connection](SCIM.md#step-2-create-a-scim-connection) for each workspace.

| Target workspace | Default role | Group-role mapping |
| --- | --- | --- |
| Demo Workspace | Member | `Admin` → Owner |
| HR Workspace | Member | None; `W_RH_view` and `W_RH_edit` stay Members |
| Executive Committee Workspace | Member | None; `Codir` stays Member |

The `Admin` mapping makes eligible group members **Demo Workspace Owners**.
It does not make them instance administrators or grant access to other workspaces.
The workspace's primary owner and instance administrators remain protected from
SCIM management.

<a href="assets/scim-demo/new-03-admin-connections.png">
  <img src="assets/scim-demo/new-03-admin-connections.png" alt="Three enabled AppFlowy SCIM connections, each scoped to its intended workspace" width="720">
</a>

*The three demo connections are enabled. The fourth connection belongs to an older demo.*

<details>
<summary>Show the Admin-to-Owner mapping</summary>

<a href="assets/scim-demo/new-02-admin-owner-mapping.png">
  <img src="assets/scim-demo/new-02-admin-owner-mapping.png" alt="Demo Workspace connection maps Admin to Owner and otherwise defaults to Member" width="720">
</a>

*Only Demo Workspace maps Admin to Owner; all three connections default to Member.*

</details>

Copy each connection's endpoint and bearer token into its matching Entra
application. Keep tokens private. Entra needs a reachable **HTTPS** endpoint;
the localhost addresses in the screenshots are local demo addresses.

If a role mapping matches a group by name, update the mapping when that group is renamed.

## 3. Create and assign the eight Entra groups

Create the eight groups listed above as **Security** groups with **Assigned**
membership. Add their descriptions. Leave Entra administrative-role assignment off.

<a href="assets/scim-demo/new-01-entra-eight-groups.png">
  <img src="assets/scim-demo/new-01-entra-eight-groups.png" alt="Entra lists all eight approved groups with Security and Assigned membership" width="720">
</a>

*The eight source groups in Entra.*

Create one enterprise application for each AppFlowy connection, then assign:

| Application target | Assigned groups |
| --- | --- |
| Demo Workspace | `Admin`, `Users`, `Super_Users`, `Codir`, `HR`, `Product` |
| HR Workspace | `W_RH_view`, `W_RH_edit` |
| Executive Committee Workspace | `Codir` |

Choose **Sync only assigned users and groups**. Start Alice in `Users` only and
Bob in `W_RH_view` only. Give Bob no separate invitation to Demo Workspace.

`Codir` is assigned to two applications, so eight Entra groups become **nine
workspace groups** in AppFlowy: six in Demo, two in HR, and one in Executive Committee.

<details>
<summary>Show the group description and application assignments</summary>

These configuration screenshots were rechecked after the demo, with provisioning paused.

<a href="assets/scim-demo/new-57-entra-users-description.png">
  <img src="assets/scim-demo/new-57-entra-users-description.png" alt="Entra Users overview shows its approved description and Assigned membership" width="720">
</a>

*Users has Assigned membership. Its description does not automatically enroll employees.*

<a href="assets/scim-demo/new-05-entra-demo-assignments.png">
  <img src="assets/scim-demo/new-05-entra-demo-assignments.png" alt="Demo Workspace application has Admin, Codir, HR, Product, Super_Users and Users assigned" width="720">
</a>

*Demo Workspace: six assigned groups.*

<a href="assets/scim-demo/new-10-entra-hr-assignments.png">
  <img src="assets/scim-demo/new-10-entra-hr-assignments.png" alt="HR Workspace application has only W_RH_edit and W_RH_view assigned" width="720">
</a>

*HR Workspace: W_RH_view and W_RH_edit.*

<a href="assets/scim-demo/new-13-entra-executive-assignment.png">
  <img src="assets/scim-demo/new-13-entra-executive-assignment.png" alt="Executive Committee Workspace application has only Codir assigned" width="720">
</a>

*Executive Committee Workspace: Codir. It is also assigned to Demo Workspace.*

</details>

The Entra application role named **User** is separate from AppFlowy's Member/Owner
roles. AppFlowy connection settings and space grants determine AppFlowy permissions.

## 4. Check mappings and start provisioning

Configure each application using the [Entra setup guide](ENTRA_SCIM_AUTO_SYNC.md).
Use these SCIM fields:

| Resource | Fields |
| --- | --- |
| User | `userName`, `active`, `displayName`, `externalId` |
| Group | `displayName`, `externalId`, `members` |

Map `userName` to the person's AppFlowy login email. The screenshots use test
addresses ending in `example.com`; do not copy that transformation for real users.

<details>
<summary>Show the user and group mappings</summary>

These saved settings were rechecked after the demo.

<a href="assets/scim-demo/new-06-entra-user-mappings.png">
  <img src="assets/scim-demo/new-06-entra-user-mappings.png" alt="Entra User mappings show userName, displayName, externalId and active" width="720">
</a>

*User mappings, including the demo-only email expression.*

<a href="assets/scim-demo/new-07-entra-group-mappings.png">
  <img src="assets/scim-demo/new-07-entra-group-mappings.png" alt="Entra Group mappings show displayName, members and externalId" width="720">
</a>

*Group name, member, and external identity mappings.*

</details>

Enable the intended group Create, Update, and Delete actions. Run **Test connection**,
then start provisioning. Check both Entra's result and the received groups in AppFlowy.

**Provision on demand** sends a change manually. To test automatic sync, change
membership and wait for a normal provisioning cycle without pressing that button.
This guide labels which method each example used.

## 5. Confirm the received groups in AppFlowy Admin

Open each connection's **SCIM groups** monitor. Expect six Demo groups, two HR
groups, and one Executive Committee group. Empty groups can also show **Synced**.

<a href="assets/scim-demo/new-08-admin-demo-groups-synced.png">
  <img src="assets/scim-demo/new-08-admin-demo-groups-synced.png" alt="Demo Workspace monitor shows six groups Synced, with Users containing one eligible member" width="720">
</a>

*Demo Workspace after an operator-restarted full scan: Users has one member; the other five groups are empty.*

<details>
<summary>Show the initial HR and Executive Committee groups</summary>

<a href="assets/scim-demo/new-19-admin-hr-groups-synced.png">
  <img src="assets/scim-demo/new-19-admin-hr-groups-synced.png" alt="HR Workspace monitor shows W_RH_view and W_RH_edit Synced" width="720">
</a>

*HR: W_RH_view has Bob; W_RH_edit is empty. These updates were delivered on demand.*

<a href="assets/scim-demo/new-26-admin-executive-group-synced.png">
  <img src="assets/scim-demo/new-26-admin-executive-group-synced.png" alt="Executive Committee monitor shows Codir Synced with no received or eligible members" width="720">
</a>

*Executive Committee: Codir is empty after on-demand setup and cleanup.*

</details>

**Synced means AppFlowy applied the data it received.** Entra may still have a newer
change waiting to be sent. It also does not confirm the person's content permissions.

**Refresh status** checks AppFlowy's state. **Retry sync** reapplies received data;
neither asks Entra to send a pending change. For errors or seat limits, see
[sync status and recovery](SCIM_OPERATIONS.md#check-sync-status).

## 6. Configure content access in AppFlowy Web

This setup lets **every member of a workspace view its configured spaces**.
Selected groups can also edit. People outside that workspace receive no access
from this setting.

For each space:

1. Open **Manage Space → General** and select **Custom**.
2. Set **Space members → Can edit** and **Everyone else → Can view**.
3. Open **Members** and add the editor groups below as **Space members**.

| Workspace | Space | Groups added as ordinary Space members for Edit |
| --- | --- | --- |
| Demo Workspace | General | `Admin`, `Super_Users` |
| Demo Workspace | Demo Intelligence | `Admin`, `Super_Users` |
| Demo Workspace | Internal IT | `Admin` |
| Demo Workspace | HR | `Admin`, `HR` |
| Demo Workspace | Product | `Admin`, `Product` |
| HR Workspace | General, Shared | `W_RH_edit` |
| Executive Committee Workspace | General, Shared | `Codir` |

<a href="assets/scim-demo/new-04-web-custom-permissions.png">
  <img src="assets/scim-demo/new-04-web-custom-permissions.png" alt="Demo Intelligence uses Custom access with Space members Can edit and everyone else Can view" width="720">
</a>

*Demo Intelligence: Space members can edit; other Demo Workspace members can view.*

Do not add `Users` or `W_RH_view` as Space members just to give them View.
With this setting, adding them to the member list would give them **Edit**.
Space owners keep Full access.

<details>
<summary>Show the editor groups for Demo Intelligence</summary>

<a href="assets/scim-demo/new-15-web-editor-group-grants.png">
  <img src="assets/scim-demo/new-15-web-editor-group-grants.png" alt="Demo Intelligence roster has Admin and Super_Users as Space members and a separate setup owner" width="720">
</a>

*Admin and Super_Users have Space member grants. This was rechecked after the demo,
when both groups were empty; the setup owner remains Space owner.*

</details>

SCIM syncs groups and membership. You configure these space grants separately;
SCIM does not create a space for each group.

**Existing spaces:** review current owners, members, direct shares, and page grants
first. Changing Public to Custom can add existing members to the list. Remove
unintended entries before giving Space members Edit. Other groups, direct grants,
and ownership can still provide access after one group is removed.

Workspace Owner gives broader administration powers than content Edit, but no
blanket access to Private spaces. Promotion does not automatically make someone
an owner of every existing Custom space; explicit space ownership can also remain
after demotion. Prepare the test spaces before the Admin scenario.

## 7. Verify the matrix as Alice and Bob

Use each person's own Web session. For every scenario, check:

1. The source membership in Entra and received membership in AppFlowy.
2. The workspace role and which pages the person can open.
3. **Edit:** save a note, reload, and confirm it from the owner's separate session.
4. **View:** try editing and confirm no change is saved.
5. **No access:** open a direct page link, not just the workspace picker.

For denied pages, first confirm the owner can open the same page. After removing
access, test both the already-open tab and a fresh session.

### Recorded baseline: view does not mean edit or cross-workspace access

With Alice in `Users` and Bob in `W_RH_view`:

| Person | Allowed | Denied |
| --- | --- | --- |
| Alice | View the five Demo Workspace spaces | HR and Executive Committee workspaces |
| Bob | View the two HR Workspace spaces | Demo and Executive Committee workspaces |

<a href="assets/scim-demo/new-09-web-users-view-general.png">
  <img src="assets/scim-demo/new-09-web-users-view-general.png" alt="Alice can read General Notes as a Users member in Demo Workspace" width="720">
</a>

*Alice reads General. Separate input and saved-content checks confirmed View-only access.*

<a href="assets/scim-demo/new-11-web-alice-hr-access-denied.png">
  <img src="assets/scim-demo/new-11-web-alice-hr-access-denied.png" alt="Alice&#x27;s direct link to an HR Workspace page returns No access" width="720">
</a>

*Alice's direct HR Workspace link is denied. The test session identifies the user and target.*

<details>
<summary>Show the other baseline access checks</summary>

<a href="assets/scim-demo/new-12-web-bob-demo-access-denied.png">
  <img src="assets/scim-demo/new-12-web-bob-demo-access-denied.png" alt="Bob&#x27;s direct link to a Demo Workspace page returns No access" width="720">
</a>

*Bob cannot open a Demo Workspace page.*

<a href="assets/scim-demo/new-14-web-alice-executive-access-denied.png">
  <img src="assets/scim-demo/new-14-web-alice-executive-access-denied.png" alt="Alice&#x27;s direct Executive Committee Workspace link returns No access" width="720">
</a>

*Alice cannot open an Executive Committee page.*

<a href="assets/scim-demo/new-16-web-hr-viewer.png">
  <img src="assets/scim-demo/new-16-web-hr-viewer.png" alt="Bob reads HR Workspace reference content as a W_RH_view member" width="720">
</a>

*Bob can read HR Workspace content; separate checks confirmed it was read-only.*

<a href="assets/scim-demo/new-18-web-workspace-member-role.png">
  <img src="assets/scim-demo/new-18-web-workspace-member-role.png" alt="People settings shows Alice as Member alongside the separate setup owner" width="720">
</a>

*People settings after the demo was reset: Alice is Member; the setup owner is Owner.*

</details>

### Recorded Super_Users addition: source, delivery, applied state, saved edit

Add Alice to `Super_Users` and keep her in `Users`. In this recorded example,
the addition was delivered **on demand**.

Alice could then edit **General** and **Demo Intelligence**, while the other
three Demo spaces stayed View-only. She remained a workspace Member with no
workspace administration or access to the other two workspaces.

<a href="assets/scim-demo/new-21-admin-super-users-synced.png">
  <img src="assets/scim-demo/new-21-admin-super-users-synced.png" alt="AppFlowy monitor shows Super_Users and Users with one eligible member each" width="720">
</a>

*AppFlowy received one member in Users and one in Super_Users.*

<details>
<summary>Show the source membership, delivery, and saved note</summary>

<a href="assets/scim-demo/new-17-entra-super-users-member.png">
  <img src="assets/scim-demo/new-17-entra-super-users-member.png" alt="Super_Users contains Alice Demo as its direct member in Entra" width="720">
</a>

*Alice appears in Super_Users in Entra.*

<a href="assets/scim-demo/new-20-entra-member-add-delivered.png">
  <img src="assets/scim-demo/new-20-entra-member-add-delivered.png" alt="Entra on-demand result reports Alice&#x27;s Add member operation succeeded" width="720">
</a>

*Entra reports a successful on-demand member addition.*

<a href="assets/scim-demo/new-22-web-super-users-edit-persisted.png">
  <img src="assets/scim-demo/new-22-web-super-users-edit-persisted.png" alt="Alice&#x27;s Demo Intelligence note survives reload after Super_Users membership" width="720">
</a>

*Alice's Demo Intelligence note remains after reload. An independent server read confirmed it saved.*

</details>

## 8. Move a member without deleting the user

### The scheduled move arrived without manually provisioning Alice

Move Alice from `Super_Users` to `HR`:

1. Save a note in Demo Intelligence as Alice.
2. In Entra, add her to `HR`, then remove her from `Super_Users`. Keep `Users`.
3. Wait for a normal provisioning cycle; do not use Provision on demand for this test.
4. Check AppFlowy's group counts, then test Alice's pages again.

<details>
<summary>Show the membership change in Entra</summary>

<a href="assets/scim-demo/new-23-entra-move-add-hr.png">
  <img src="assets/scim-demo/new-23-entra-move-add-hr.png" alt="Entra HR group contains Alice Demo after the target membership addition" width="720">
</a>

*Alice is added to HR.*

<a href="assets/scim-demo/new-24-entra-move-remove-super-users.png">
  <img src="assets/scim-demo/new-24-entra-move-remove-super-users.png" alt="Entra Super_Users group has no members after Alice is removed" width="720">
</a>

*Alice is removed from Super_Users. Her account remains in Users.*

</details>

Before delivery, AppFlowy still showed the old membership even though the groups
were marked Synced:

<a href="assets/scim-demo/new-33-admin-awaiting-upstream-move.png">
  <img src="assets/scim-demo/new-33-admin-awaiting-upstream-move.png" alt="AppFlowy still shows the previously received Super_Users membership while the upstream move waits for delivery" width="720">
</a>

*Waiting: Super_Users has one member; HR is empty.*

The next normal cycle delivered the change:

<a href="assets/scim-demo/new-35-admin-scheduled-member-move-applied.png">
  <img src="assets/scim-demo/new-35-admin-scheduled-member-move-applied.png" alt="AppFlowy applies Alice to HR, removes her from Super_Users, and retains Users" width="720">
</a>

*After delivery: HR has one member; Super_Users is empty; Users still has Alice.*

Alice could edit the **HR space inside Demo Workspace** and view its other four
spaces. She still had no access to the separate HR Workspace. Her earlier note,
account, and workspace Member role remained intact.

<details>
<summary>Show the completed cycle and retained content</summary>

<a href="assets/scim-demo/new-36-entra-scheduled-cycle-completed.png">
  <img src="assets/scim-demo/new-36-entra-scheduled-cycle-completed.png" alt="Entra reports the completed normal incremental provisioning cycle" width="720">
</a>

*Entra completed the normal cycle. The seventh group is the separate lifecycle test group.*

<a href="assets/scim-demo/new-37-web-move-old-note-now-viewer.png">
  <img src="assets/scim-demo/new-37-web-move-old-note-now-viewer.png" alt="Alice&#x27;s saved Demo Intelligence note remains visible after the group move" width="720">
</a>

*The old Demo Intelligence note remains. This content image looks the same as before;
separate checks confirmed View after reload.*

<a href="assets/scim-demo/new-38-web-hr-team-edit-persisted.png">
  <img src="assets/scim-demo/new-38-web-hr-team-edit-persisted.png" alt="Alice&#x27;s new HR team note remains after reload following the scheduled move" width="720">
</a>

*Alice saved a new note in the HR space. Its saved content was independently confirmed.*

</details>

### The next HR → Product move was delivered on demand

Next, add Alice to `Product`, remove her from `HR`, and keep `Users`. This recorded
move used **Provision on demand**. Product became editable; the other four spaces
became View-only. Alice stayed a Member and kept her earlier notes.

<details>
<summary>Show the Product membership and saved edit</summary>

<a href="assets/scim-demo/new-42-admin-product-member-synced.png">
  <img src="assets/scim-demo/new-42-admin-product-member-synced.png" alt="AppFlowy shows Alice in Product and Users, with HR now empty" width="720">
</a>

*Product has Alice; HR is empty. The temporary lifecycle group has not yet been deleted.*

<a href="assets/scim-demo/new-43-web-product-edit-persisted.png">
  <img src="assets/scim-demo/new-43-web-product-edit-persisted.png" alt="Alice&#x27;s Product note remains after reload following the move from HR" width="720">
</a>

*Alice's new Product note was confirmed saved.*

</details>

### Bob's HR editor and restored-viewer phases

Move Bob from `W_RH_view` to `W_RH_edit`, save a note, then move him back.
Both changes in this demo used **Provision on demand**.

Bob stayed a Member of HR Workspace throughout. He gained Edit in its two spaces,
then returned to View. His saved note remained, and the other workspaces stayed denied.

**The already-open page did not immediately become read-only.** It still allowed
local typing after Edit was removed:

<a href="assets/scim-demo/new-31-web-stale-editor-local-only.png">
  <img src="assets/scim-demo/new-31-web-stale-editor-local-only.png" alt="Bob&#x27;s stale editor displays a locally typed sentence after Edit was revoked" width="720">
</a>

*The last sentence was typed after permission was removed. Independent server reads
confirmed it did not save. A fresh Bob session was read-only.*

<details>
<summary>Show Bob's editor, viewer, and denied-access checks</summary>

<a href="assets/scim-demo/new-29-admin-hr-editor-synced.png">
  <img src="assets/scim-demo/new-29-admin-hr-editor-synced.png" alt="HR monitor shows W_RH_edit with Bob and W_RH_view empty during the editor phase" width="720">
</a>

*Editor phase: W_RH_edit has one member and W_RH_view is empty.*

<a href="assets/scim-demo/new-28-web-hr-editor-persisted.png">
  <img src="assets/scim-demo/new-28-web-hr-editor-persisted.png" alt="Bob&#x27;s HR Workspace note survives reload while he is an editor" width="720">
</a>

*Bob saved this note while he had Edit access.*

<a href="assets/scim-demo/new-30-web-restored-viewer-fresh-session.png">
  <img src="assets/scim-demo/new-30-web-restored-viewer-fresh-session.png" alt="A fresh Bob viewer session retains the authorized note but not the revoked local edit" width="720">
</a>

*After returning to View, the saved note remains and the later local sentence is absent.
The image has no read-only badge; input checks confirmed View separately.*

<a href="assets/scim-demo/new-32-web-bob-executive-access-denied.png">
  <img src="assets/scim-demo/new-32-web-bob-executive-access-denied.png" alt="The restored Bob viewer&#x27;s fresh session is denied a direct Executive Committee page link" width="720">
</a>

*Bob's fresh session cannot open an Executive Committee page.*

</details>

Keep at least one valid application assignment during a group move. Leaving all
assignments can cause workspace offboarding, which is the next example.

## 9. Test workspace offboarding and administrator demotion

### Remove only Executive Committee access

1. Remove Alice's previous editor group and add her to `Codir`. Keep `Users`.
2. Confirm she can view Demo Workspace and edit Executive Committee content.
3. Save a note there, then remove her from `Codir`.
4. Confirm Entra sends the Executive application's user deactivation.
5. Open the Executive page in a fresh Alice session and check the note as the owner.

In this run, Executive admission arrived **automatically**; its user deactivation
was delivered **on demand**. Demo's Codir changes were also on demand.

<a href="assets/scim-demo/new-49-web-offboarded-user-direct-link-denied.png">
  <img src="assets/scim-demo/new-49-web-offboarded-user-direct-link-denied.png" alt="A fresh Alice session cannot open the direct Executive Committee page link after offboarding" width="720">
</a>

*After deactivation, Alice's fresh session cannot open the Executive page.*

Alice kept her active account and Demo Workspace access through `Users`.
The owner could still read her Executive note. The old Alice tab retained cached
content and allowed local typing, but that later text did not save.

<details>
<summary>Show Executive membership, deactivation, and retained content</summary>

<a href="assets/scim-demo/new-46-admin-executive-member-synced.png">
  <img src="assets/scim-demo/new-46-admin-executive-member-synced.png" alt="Executive Committee monitor shows Codir with one eligible synced member" width="720">
</a>

*Codir has one member in Executive Committee Workspace.*

<a href="assets/scim-demo/new-45-web-executive-edit-persisted.png">
  <img src="assets/scim-demo/new-45-web-executive-edit-persisted.png" alt="Alice&#x27;s Executive Committee note remains after reload as a workspace Member" width="720">
</a>

*Alice saved this Executive note as a workspace Member.*

<a href="assets/scim-demo/new-47-entra-workspace-offboarding.png">
  <img src="assets/scim-demo/new-47-entra-workspace-offboarding.png" alt="Entra reports a successful connection-scoped active True to False update" width="720">
</a>

*Entra reports active changing from True to False for the Executive connection.*

<a href="assets/scim-demo/new-48-web-offboarded-user-note-retained.png">
  <img src="assets/scim-demo/new-48-web-offboarded-user-note-retained.png" alt="The setup owner still reads Alice&#x27;s Executive note after she loses workspace access" width="720">
</a>

*The setup owner can still read Alice's note after her workspace access is removed.*

</details>

### Add and remove workspace administration

Add Alice to `Admin`, confirm the Owner mapping, then remove her from `Admin`
while keeping `Users`. Both changes here were delivered **on demand**.

| Membership | Demo Workspace role | Result |
| --- | --- | --- |
| Users + Admin | Owner | Workspace administration and Edit in the five configured spaces |
| Users only | Member | View in those spaces; workspace administration removed |

Neither state grants instance administration or HR/Executive workspace access.
Do not create spaces during the Owner test; that could add separate ownership
rights that survive removal from `Admin`.

<a href="assets/scim-demo/new-51-web-admin-workspace-owner-role.png">
  <img src="assets/scim-demo/new-51-web-admin-workspace-owner-role.png" alt="People settings shows Alice as Owner alongside the separate original setup owner" width="720">
</a>

*After promotion: Alice is Owner alongside the separate setup owner.*

<a href="assets/scim-demo/new-54-web-demoted-workspace-member-role.png">
  <img src="assets/scim-demo/new-54-web-demoted-workspace-member-role.png" alt="People settings shows Alice returned to Member while the original setup owner remains Owner" width="720">
</a>

*After removal: Alice is Member again. The setup owner is unchanged.*

<details>
<summary>Show the Admin membership and note before and after demotion</summary>

<a href="assets/scim-demo/new-50-admin-owner-group-synced.png">
  <img src="assets/scim-demo/new-50-admin-owner-group-synced.png" alt="AppFlowy shows Admin and Users each with Alice as an eligible synced member" width="720">
</a>

*Admin and Users each contain Alice.*

<a href="assets/scim-demo/new-52-web-admin-edit-persisted.png">
  <img src="assets/scim-demo/new-52-web-admin-edit-persisted.png" alt="Alice&#x27;s Internal IT note remains after reload during the Admin phase" width="720">
</a>

*Alice saved an Internal IT note while she had Admin access.*

<a href="assets/scim-demo/new-53-web-demoted-member-readonly-note-retained.png">
  <img src="assets/scim-demo/new-53-web-demoted-member-readonly-note-retained.png" alt="Alice&#x27;s Internal IT note remains visible after workspace-role demotion" width="720">
</a>

*The note remains after demotion. Separate checks confirmed View after reload.*

</details>

## 10. Test group creation, rename and deletion

Use an empty test group so the eight regular groups stay unchanged:

| Action in Entra | Expected AppFlowy result | Delivery in this demo |
| --- | --- | --- |
| Create SCIM_Lifecycle_Demo and assign it to the Demo application | A seventh group appears | Automatic cycle |
| Rename it to SCIM_Lifecycle_Renamed | The same group gets the new name | On demand |
| Delete it in Entra | The group disappears; the six regular groups remain | Automatic cycle |

<a href="assets/scim-demo/new-34-admin-temporary-group-created.png">
  <img src="assets/scim-demo/new-34-admin-temporary-group-created.png" alt="The temporary lifecycle group appears as a seventh Synced Demo Workspace group" width="720">
</a>

*Created: the temporary group appears as the seventh Demo group.*

<a href="assets/scim-demo/new-44-admin-temporary-group-deleted.png">
  <img src="assets/scim-demo/new-44-admin-temporary-group-deleted.png" alt="AppFlowy shows only the six regular Demo groups after scheduled temporary-group deletion" width="720">
</a>

*Deleted: only the six regular groups remain. These counts were captured during
the separate Codir test, when Alice belonged to Users and Codir.*

The rename kept the same group identity. Deleting this empty group did not delete
users or saved content. Deleting a populated group was not tested.

<details>
<summary>Show the source creation, assignment, rename, and deletion</summary>

<a href="assets/scim-demo/new-25-entra-create-temporary-group.png">
  <img src="assets/scim-demo/new-25-entra-create-temporary-group.png" alt="New Entra group form for the separate SCIM_Lifecycle_Demo group" width="720">
</a>

*Create the separate test group. This is the form before delivery.*

<a href="assets/scim-demo/new-27-entra-lifecycle-assigned.png">
  <img src="assets/scim-demo/new-27-entra-lifecycle-assigned.png" alt="The separate SCIM_Lifecycle_Demo group is assigned to the Demo Workspace application" width="720">
</a>

*Assign it to the Demo application. The application heading is outside this capture.*

<a href="assets/scim-demo/new-39-entra-group-rename-delivered.png">
  <img src="assets/scim-demo/new-39-entra-group-rename-delivered.png" alt="Entra reports the temporary group&#x27;s displayName change to SCIM_Lifecycle_Renamed" width="720">
</a>

*Entra reports the name change.*

<a href="assets/scim-demo/new-40-admin-temporary-group-renamed.png">
  <img src="assets/scim-demo/new-40-admin-temporary-group-renamed.png" alt="AppFlowy shows the same empty group as SCIM_Lifecycle_Renamed and Synced" width="720">
</a>

*AppFlowy shows the new name on the empty group.*

<a href="assets/scim-demo/new-41-entra-temporary-source-group-deleted.png">
  <img src="assets/scim-demo/new-41-entra-temporary-source-group-deleted.png" alt="Entra no longer finds the temporary source group after its deletion" width="720">
</a>

*Entra no longer finds the source group. AppFlowy removes its copy only after the
deletion is delivered, as shown above.*

</details>

Removing an application assignment and deleting a source group are different
actions. Always check what Entra sent and whether AppFlowy applied it.

## Verified results

The demo checked all eight groups against the current test spaces:

| Check | Result |
| --- | --- |
| Group names and membership | Changes arrived in the intended workspace |
| Group moves | Access changed; accounts and previously saved notes remained |
| Workspace offboarding | Executive access was removed; Demo access and the account remained |
| Admin role removal | Owner returned to Member; saved content remained |
| Fresh-session access | Viewers could not save edits; unauthorized direct links were denied |
| Already-open pages | Old content and local typing could remain; revoked edits did not save |

The same Alice and Bob accounts remained active, seat use stayed at three of
three, and all six newly saved notes survived. The primary owners stayed unchanged;
attempts to change protected owners were not part of this test.

These were **text-document and permission checks**. They do not prove page/space
creation rules, database operations, access to future or Private spaces, overriding
denies, or license-expansion retry. See the [current limitations](#what-remains-unsupported).

Screenshots show selected states; separate input and server checks confirmed access
and saved content. Some before/after images look identical because the content
was retained. The [evidence index](assets/scim-demo/CAPTURE_NOTES.md#requirement-evidence-index)
records each check and its limits.

The run used a local development setup on October 11, 2026. Cloud reported
self-hosted **0.19.0**, and its exact running build was not verified. This is not
a release certification. Full timings, delivery methods, and build details are in
the [capture notes](assets/scim-demo/CAPTURE_NOTES.md).

## Finish the temporary demo

1. Return Alice to `Users` only and Bob to `W_RH_view` only.
2. Check that their original access and saved notes remain.
3. Pause the three Entra provisioning jobs and disable their AppFlowy connections.
4. Stop any temporary public tunnel or proxy.
5. Cancel the Entra trial when finished and verify renewal is disabled.

<a href="assets/scim-demo/new-55-admin-baseline-restored.png">
  <img src="assets/scim-demo/new-55-admin-baseline-restored.png" alt="The final Demo group monitor shows Users with one member and the other five groups empty" width="720">
</a>

*Restored Demo groups: Users has one member; the other five groups are empty.*

<a href="assets/scim-demo/new-56-admin-demo-connections-disabled.png">
  <img src="assets/scim-demo/new-56-admin-demo-connections-disabled.png" alt="All three demo AppFlowy connections show Disabled after the jobs are paused" width="720">
</a>

*The three demo connections are Disabled. The older fourth connection was already disabled.*

The recorded demo finished in this state. The temporary public connection was
closed; groups, accounts, workspaces, and notes were kept. Trial cancellation
remains the account owner's action.

To repeat the demo, provide a reachable HTTPS endpoint, enable and test the
connections, and restart provisioning.

For troubleshooting, role precedence, or seat recovery, see [SCIM operations](SCIM_OPERATIONS.md).
