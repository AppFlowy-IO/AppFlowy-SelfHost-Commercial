# SCIM group synchronization and permissions: a complete example

[Documentation](README.md) / [SCIM setup](SCIM.md) / [Entra setup](ENTRA_SCIM_AUTO_SYNC.md)

Follow a group change through **Microsoft Entra ID → AppFlowy Admin → AppFlowy
Web**. This example uses eight groups across three workspaces and shows where
synchronization ends and content permission settings begin.

Click any screenshot to view it at full size.

- **Entra ID:** choose which people belong to each group and application.
- **AppFlowy Admin:** receive those groups into the right workspace and map workspace roles.
- **AppFlowy Web:** grant groups access to spaces, then verify as the affected person.

Once these grants exist, a synced membership change changes the person's access;
you do not need to delete or recreate the user.

**The complete requested permission matrix is not yet supported.** Group sync,
workspace roles and the content-access recipe below are separate from the missing
space/workspace creation controls. Read [what remains unsupported](#what-remains-unsupported)
before using this example in a real installation.

Navigation: [permission matrix](#the-permission-matrix) ·
[workspace setup](#1-prepare-three-workspaces-and-two-test-users) ·
[Entra setup](#3-create-and-assign-the-eight-entra-groups) ·
[space permissions](#6-configure-content-access-in-appflowy-web) ·
[group moves](#8-move-a-member-without-deleting-the-user) ·
[results](#verified-results).

Recorded examples: [viewer and denied access](#recorded-baseline-view-does-not-mean-edit-or-cross-workspace-access) ·
[Super_Users editor](#recorded-super_users-addition-source-delivery-applied-state-saved-edit) ·
[HR viewer/editor change](#bobs-hr-editor-and-restored-viewer-phases) ·
[workspace offboarding](#remove-only-executive-committee-access) ·
[Admin role](#add-and-remove-workspace-administration) ·
[group lifecycle](#10-test-group-creation-rename-and-deletion).

## The permission matrix

The tables below show the groups and requested permissions used in this example.

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

The `Users` description is an organization rule to configure in the directory.
AppFlowy does not automatically add employees because a group is named `Users`.
Keep HR-only users out of any automatic `Users` rule: otherwise that rule would
intentionally provision them into Demo Workspace.

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

**How to read the table:**

- **Admin** means administration of **Demo Workspace**, not access to the instance
  Admin frontend. Its Edit value maps to the AppFlowy workspace **Owner** role.
- **General, Demo Intelligence, Internal IT, HR and Product** are spaces inside
  Demo Workspace. **HR WORKSPACE** is a separate confidential workspace; it is
  not the HR space or the `HR` group. **EXECUTIVE COMMITTEE WORKSPACE** is also
  separate.
- View/Edit in a content column is not an AppFlowy workspace role. Ordinary
  viewers and editors remain workspace **Members**.
- **In this example**, No Access means this row grants no access. Another
  legitimate group, direct share or workspace membership may still grant access.
  This is an assumption for the demonstration: the requester has not confirmed
  whether No Access must override other grants. Such an overriding deny is not
  implemented by this example.
- The table is the **requested result**, not a claim that every operation in
  every cell passed. Document edits, database mutations, administration and
  creation rules are different checks.

### Requested creation rules

The following rules describe what each group should be allowed to create:

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

“With Edit rights” is a condition. A View-only row does not gain page creation
merely because its creation rule contains that sentence. Creating pages also depends
on the space's sidebar policy; editing an existing page does not test page creation.

Creating **a whole workspace** is separate from creating a space inside one.
The requested deployment additionally limits whole-workspace creation to selected
people. Do not assume that every `Admin` member belongs on that selected-person
list; that policy needs its own configuration and verification.

## What remains unsupported

These observations describe the inspected local demo. Cloud's server-info reports
`0.19.0, self_hosted`; its exact running source build is unverified. Admin and Web
are development runtimes. This is not a verified release-build certification.

| Requirement | What is available or missing |
| --- | --- |
| Editor groups edit; every other admitted workspace member views | The Custom-space recipe below supports this using two audience levels |
| Explicit Viewer and Editor groups while everyone else is denied | Ordinary Space Members share one permission level; independent View/Edit levels per group need implementation |
| Members edit content but cannot create spaces | Backend policy exists, but its configuration controls are absent from the inspected clients; this is not a completed UI feature |
| Only selected Members or groups create spaces | Requires additional implementation |
| Only selected people create whole workspaces | Requires additional implementation and operator/client controls |
| Automatic access across every existing and future space | Explicit grants to the named spaces do not establish this; scope and exceptions need separate implementation/verification |
| Immediate permission refresh in an already-open Web page | An open page stayed visible/editable after Bob lost Edit or Alice lost workspace access; fresh sessions enforced the new access and revoked local edits did not save |

The inspected runtime reported **Members and Owners** as its space-creation
policy in all three workspaces. This example must not be deployed as a completed
no-new-space policy. A false “manage this space” capability concerns an existing
space; it does not prove that a Member cannot create a new one.

Workspace Owner is broader than content Edit. It allows workspace administration
and management of non-private Custom spaces on the inspected runtime. It is not
a blanket bypass into Private spaces. The protected SCIM accounts are the
workspace's recorded primary owner and instance system administrators; eligible
ordinary users can receive the workspace Owner role through a group mapping.

## 1. Prepare three workspaces and two test users

Use a dedicated test tenant and AppFlowy installation. Check the current
[Entra license and network requirements](ENTRA_SCIM_AUTO_SYNC.md#step-1-check-the-license-and-network-requirements)
and [SCIM prerequisites](SCIM.md#before-you-begin).

Create or identify:

| Workspace | Spaces used in this example | Purpose |
| --- | --- | --- |
| Demo Workspace | General, Demo Intelligence, Internal IT, HR, Product | Shared company content |
| HR Workspace | General and Shared | Confidential team content |
| Executive Committee Workspace | General and Shared | Executive content |

Isolation checks in this guide compare these **three target workspaces**.
Review any pre-existing memberships separately; an older unrelated demo workspace
was retained in the test installation.

The two spaces literally named **Shared** in the last two workspaces are separate
spaces. The permission matrix defines workspace access there; these test spaces
let us verify that access within each workspace.

Use a setup owner outside SCIM and two synthetic identities, **Alice Demo** and
**Bob Demo**. With a three-seat installation, reuse these accounts across the
scenarios; eight groups do not require eight user accounts. Keep the setup owner
separate from the `Admin` test subject. Seeing all workspaces as the setup owner
does not prove a normal user's isolation.

The SCIM email must match the person's AppFlowy sign-in identity. SCIM provisions
accounts and memberships; it does not sign users in. See
[Authentication](AUTHENTICATION.md) for the login setup.

The recorded setup uses fresh reference documents with the workspace/space
names above. Each target must load for the authorized setup owner before an
access-denied result is counted as a permission test.

## 2. Create one AppFlowy SCIM connection per workspace

In AppFlowy Admin, open **Authentication → SCIM Provisioning** and
[create a connection](SCIM.md#step-2-create-a-scim-connection) for each workspace.

| Target workspace | Default role | Group-role mapping |
| --- | --- | --- |
| Demo Workspace | Member | `Admin` → Owner |
| HR Workspace | Member | None; `W_RH_view` and `W_RH_edit` stay Members |
| Executive Committee Workspace | Member | None; `Codir` stays Member |

The default Member role grants workspace membership, not Edit on every space.
Only the Demo Workspace connection maps `Admin` to Owner. That mapping does not
make a person an instance administrator or admit them to the other workspaces.

Copy each endpoint and one-time bearer token directly into its matching Entra
application. Keep tokens out of screenshots, documentation and logs. A connection
is scoped to a workspace; do not reuse its token for another workspace.

If an existing mapping matches a group **name**, update that mapping when renaming
the group. A matching external identifier can avoid this name dependency when
supported by the configured mapping. Renaming a group must not silently drop or
change the intended Owner mapping.

<a href="assets/scim-demo/new-03-admin-connections.png">
  <img src="assets/scim-demo/new-03-admin-connections.png" alt="Three enabled AppFlowy SCIM connections, each scoped to its intended workspace" width="720">
</a>

*Each new connection defaults to Member. Demo Workspace alone has a role mapping.
Workspace identifiers are explicitly hidden; the bottom disabled connection is
from a separate earlier demo. The displayed localhost address is local development
context, not the reachable HTTPS endpoint supplied to Entra.*

<a href="assets/scim-demo/new-02-admin-owner-mapping.png">
  <img src="assets/scim-demo/new-02-admin-owner-mapping.png" alt="Demo Workspace connection maps Admin to Owner and otherwise defaults to Member" width="720">
</a>

*The saved connection's mapping is shown for inspection. Its workspace identifier
is hidden. This configuration alone does not prove that a test user has received
the Owner role; the administrator scenario checks that separately.*

## 3. Create and assign the eight Entra groups

Create the groups in the [group-purpose table](#groups-and-their-purpose), using
**Security** and **Assigned** membership for this controlled demonstration.
Enter the corresponding descriptions. Leave the Entra administrative-role
assignment toggle off: Entra administrator roles are not AppFlowy workspace roles.

Use three dedicated enterprise applications, one for each connection:

| Application target | Assigned groups |
| --- | --- |
| Demo Workspace | `Admin`, `Users`, `Super_Users`, `Codir`, `HR`, `Product` |
| HR Workspace | `W_RH_view`, `W_RH_edit` |
| Executive Committee Workspace | `Codir` |

There are **eight source groups and nine workspace-scoped projections**: six,
two and one. `Codir` is one source group assigned to two applications. Each
AppFlowy connection still has a separate projected group and workspace permissions.

Use **Sync only assigned users and groups**. Start Alice in `Users` only and Bob
in `W_RH_view` only. Keep Bob out of the Demo Workspace application and do not give
him a separate invitation or membership there.

<a href="assets/scim-demo/new-01-entra-eight-groups.png">
  <img src="assets/scim-demo/new-01-entra-eight-groups.png" alt="Entra lists all eight approved groups with Security and Assigned membership" width="720">
</a>

*The source groups use the names defined above. Their descriptions follow the
purpose table above. This list confirms group existence, not delivered membership.*

<a href="assets/scim-demo/new-57-entra-users-description.png">
  <img src="assets/scim-demo/new-57-entra-users-description.png" alt="Entra Users overview shows its approved description and Assigned membership" width="720">
</a>

*This post-run configuration check shows the Users group description.
Membership is **Assigned**: the description does not automatically enroll new
employees. An actual directory rule for that behavior is outside this example.*

<a href="assets/scim-demo/new-05-entra-demo-assignments.png">
  <img src="assets/scim-demo/new-05-entra-demo-assignments.png" alt="Demo Workspace application has Admin, Codir, HR, Product, Super_Users and Users assigned" width="720">
</a>

*This configuration was rechecked after the run, with provisioning paused.
The named Demo application has these six groups assigned; the two confidential
HR groups are absent. User is an Entra app role, not an AppFlowy workspace role.*

<a href="assets/scim-demo/new-10-entra-hr-assignments.png">
  <img src="assets/scim-demo/new-10-entra-hr-assignments.png" alt="HR Workspace application has only W_RH_edit and W_RH_view assigned" width="720">
</a>

*This post-run configuration recheck identifies the separate HR application and
its two groups. Application scope is different from effective space permissions.*

<a href="assets/scim-demo/new-13-entra-executive-assignment.png">
  <img src="assets/scim-demo/new-13-entra-executive-assignment.png" alt="Executive Committee Workspace application has only Codir assigned" width="720">
</a>

*This post-run recheck shows Codir assigned to the named Executive application.
Codir also appears in Demo: one source group serves two scoped connections.*

For each application, save its corresponding AppFlowy endpoint/token and run the
connection test. The endpoint must be HTTPS and reachable from Microsoft; a local
loopback address is not reachable from Entra. Follow the
[Entra setup guide](ENTRA_SCIM_AUTO_SYNC.md) for the provider controls.

The application assignment role named **User** in Entra is not AppFlowy's
Member/Owner role. Application assignment sets provisioning scope; the AppFlowy
connection and space settings determine the resulting AppFlowy permissions.

This is a cloud-managed Entra demonstration. It does not verify import from a
Windows AD server or nested-group expansion. For that upstream stage, follow
[AD to SCIM](AD_SCIM_AUTO_SYNC.md) and validate the connector separately.

## 4. Check mappings and start provisioning

Use the supported mappings for the running AppFlowy version. This demonstration
uses these core fields:

| Resource | SCIM attributes |
| --- | --- |
| User | `userName`, `active`, `displayName`, `externalId` |
| Group | `displayName`, `externalId`, `members` |

Select the intended Create, Update and Delete actions for groups. Their presence
in configuration is not proof that each operation succeeded.

The demo uses reserved `example.com` emails for synthetic users. In production,
map `userName` to the person's existing AppFlowy sign-in email; do not copy a demo
email transformation or use it to rename an existing login email.

<a href="assets/scim-demo/new-06-entra-user-mappings.png">
  <img src="assets/scim-demo/new-06-entra-user-mappings.png" alt="Entra User mappings show userName, displayName, externalId and active" width="720">
</a>

*The named Demo application's mapping was rechecked after the run. Its reserved
example.com expression is for synthetic identities; production userName must
match the real person's AppFlowy sign-in email.*

<a href="assets/scim-demo/new-07-entra-group-mappings.png">
  <img src="assets/scim-demo/new-07-entra-group-mappings.png" alt="Entra Group mappings show displayName, members and externalId" width="720">
</a>

*This post-run recheck shows separate mappings for name, membership and external
identity. A mapping screen does not establish a successful lifecycle operation.*

Start provisioning for each application. Separate three observations:

1. **Test connection** checks connectivity and credentials.
2. A **scheduled** or **on-demand** provisioning result shows what Entra sent.
3. AppFlowy's applied state and the user's permissions show the result.

On-demand provisioning is useful for setup and troubleshooting, but it is not
proof that a scheduled cycle ran. Label the delivery method for each scenario.

## 5. Confirm the received groups in AppFlowy Admin

Open each connection's **SCIM groups** monitor. Confirm the expected six, two and
one groups and compare the member counts against the completed Entra delivery.
Empty groups can be Synced too.

<a href="assets/scim-demo/new-08-admin-demo-groups-synced.png">
  <img src="assets/scim-demo/new-08-admin-demo-groups-synced.png" alt="Demo Workspace monitor shows six groups Synced, with Users containing one eligible member" width="720">
</a>

*After an operator-triggered **Restart provisioning** full scan, the six Demo
group-name updates arrived successfully. The same groups and memberships were
retained; Users has Alice and the other
five groups are empty at this checkpoint. This is a manually restarted full
scan, not evidence of a later scheduled membership move. The portal clock in
the image is UTC+8.*

<a href="assets/scim-demo/new-19-admin-hr-groups-synced.png">
  <img src="assets/scim-demo/new-19-admin-hr-groups-synced.png" alt="HR Workspace monitor shows W_RH_view and W_RH_edit Synced" width="720">
</a>

*These group names were delivered using **Provision on demand**. W_RH_view has
Bob as its one eligible member; W_RH_edit is empty at
this viewer checkpoint. Later editor/viewer transitions have separate results.*

<a href="assets/scim-demo/new-26-admin-executive-group-synced.png">
  <img src="assets/scim-demo/new-26-admin-executive-group-synced.png" alt="Executive Committee monitor shows Codir Synced with no received or eligible members" width="720">
</a>

*Codir's name update arrived on demand. A later targeted on-demand reconciliation
removed a stale received membership; this capture shows **0/0 eligible and
0 received**. The account was not
deleted. Alice's lack of Executive Committee access was checked separately.*

The subsequent full check confirmed all nine projections had the approved names
and retained their original source, SCIM and workspace-group identities. Alice had already
joined Super_Users by this checkpoint; it is not the earlier Users-only baseline.

**Synced** means AppFlowy applied the group name and membership it has received.
It does not prove that Entra has sent its latest change, that the person can sign
in, or that their content permissions match the matrix.

**Refresh status** reads AppFlowy's state; it does not trigger Entra. A retry
reapplies received data and cannot pull an upstream change that has not arrived.
Inspect Pending, Waiting for seats or Needs attention before continuing; see
[sync status and recovery](SCIM_OPERATIONS.md#check-sync-status).

## 6. Configure content access in AppFlowy Web

This recipe assumes **every admitted member of the workspace may view its chosen
spaces**. It is not a strict group-only viewer allowlist. A manually admitted
workspace member can also receive View through Everyone else.

1. Prepare the spaces before promoting a test user to workspace Owner.
2. Open **Manage Space → General** and choose **Custom**.
3. Set **Space members = Can edit** and **Everyone else = Can view**. Save/confirm
   changes as required by the UI.
4. Open **Members**, find each editor group and add it as a **Space member** using
   the table below. Space owners retain Full access.
5. Do **not** add `Users` or `W_RH_view` to the ordinary member roster merely to
   give them View: with this collective member setting, adding them grants Edit.

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

*Everyone else means eligible members of Demo Workspace. People outside that
workspace do not gain access from this audience. Ordinary Space members share
one collective Edit level; this is not an independent per-group level selector.*

<a href="assets/scim-demo/new-15-web-editor-group-grants.png">
  <img src="assets/scim-demo/new-15-web-editor-group-grants.png" alt="Demo Intelligence roster has Admin and Super_Users as Space members and a separate setup owner" width="720">
</a>

*This configuration was rechecked after the viewer baseline was restored. Admin
and Super_Users still hold the collective Space member grant, but both groups
are now empty. The separate setup owner remains Space owner; its unique account
identifier is hidden. This is not the earlier active-editor membership snapshot.*

SCIM creates/synchronizes the directory groups; it does not create a space for
each group or automatically choose these grants. Removing one group grant also
does not remove an independent direct grant, another group grant or ownership.

**Existing spaces:** inspect current owners, direct/group members, page grants
and visibility before applying this recipe. Converting Public to Custom may
materialize existing members into the roster. Review unintended editor entries
before switching the shared member level to Edit. Removing a space assignment
is different from removing the person from the workspace.

**Owner changes:** a later workspace Owner promotion does not populate every
pre-existing Custom-space ownership row. Conversely, independent explicit space
ownership may survive demotion. Create the demo spaces before the Owner phase
and do not create new spaces during that phase.

## 7. Verify the matrix as Alice and Bob

Use each test person's own Web session. Keep an independent authorized reader
session to check whether content really saved. Use direct links as well as the
workspace picker; absence from the sidebar alone is not an authorization test.

| Scenario | Source membership | Expected content and workspace result |
| --- | --- | --- |
| Baseline viewer | Alice: `Users` | Demo Workspace Member; all five spaces View; no HR/Executive Committee workspace access |
| Champion | Alice: `Users` + `Super_Users` | General/Demo Intelligence Edit; other three spaces View; remains Member |
| HR team | Alice: `Users` + `HR` | HR space Edit; other four Demo spaces View; no HR Workspace access |
| Product team | Alice: `Users` + `Product` | Product space Edit; other four Demo spaces View |
| Executive | Alice: `Users` + `Codir` | Demo Workspace View and Executive Committee content Edit; Member in both; HR Workspace denied |
| Workspace administrator | Alice: `Users` + `Admin` | Demo Workspace Owner; five explicit content grants Edit; other workspaces and instance administration denied |
| Confidential viewer | Bob: `W_RH_view` | HR Workspace Member/View; Demo and Executive Committee workspaces denied |
| Confidential editor | Bob: `W_RH_edit` | HR Workspace Member/Edit; other workspaces denied |

Reset the previous editor membership before assessing the next isolated row.
Keep `Users` during Alice's Demo Workspace moves so she remains in provisioning
scope. Do not test a group move by deleting and recreating an account.

For each scenario:

1. Confirm the source memberships, provider delivery and applied group state.
2. Check the workspace role and the relevant readable/editable pages.
3. For Edit, type a unique note, reload and check from an independent reader.
4. For View, verify the editor is read-only and attempted changes do not save.
   Confirm the absence of the attempted change through an independent fresh
   reader and the server state; visible local text is not evidence of persistence.
5. Open direct links to excluded workspaces and check access is denied. For a
   previously authorized page, also retest the existing tab after access removal;
   a hidden sidebar item is not sufficient.
6. Check management separately: ordinary rows remain Members without workspace
   administration; `Admin` gets administration only in Demo Workspace.
7. Compare the same account identity and licensed seat count privately.

### Recorded baseline: view does not mean edit or cross-workspace access

<a href="assets/scim-demo/new-09-web-users-view-general.png">
  <img src="assets/scim-demo/new-09-web-users-view-general.png" alt="Alice can read General Notes as a Users member in Demo Workspace" width="720">
</a>

*The document's reference text describes the intended setup; it is not proof of
permission by itself. The editor was independently inspected as read-only. An
actual click-and-type attempt did not insert the test marker, and the fresh
server read confirmed the saved document was unchanged.*

<a href="assets/scim-demo/new-11-web-alice-hr-access-denied.png">
  <img src="assets/scim-demo/new-11-web-alice-hr-access-denied.png" alt="Alice&#x27;s direct link to an HR Workspace page returns No access" width="720">
</a>

*This is Alice, admitted to Demo Workspace through Users, opening a direct HR
Workspace page link. The URL and identity are omitted from the image; matching
private session/target checks establish both. The target is readable by its
authorized owner.*

<a href="assets/scim-demo/new-12-web-bob-demo-access-denied.png">
  <img src="assets/scim-demo/new-12-web-bob-demo-access-denied.png" alt="Bob&#x27;s direct link to a Demo Workspace page returns No access" width="720">
</a>

*This is Bob's separate session opening a direct Demo Workspace link. The denied
screen naturally looks the same as Alice's, but the account and target are
different. Hiding a sidebar item alone would not establish this boundary.*

<a href="assets/scim-demo/new-14-web-alice-executive-access-denied.png">
  <img src="assets/scim-demo/new-14-web-alice-executive-access-denied.png" alt="Alice&#x27;s direct Executive Committee Workspace link returns No access" width="720">
</a>

*The same Alice session also failed a direct link into Executive Committee
Workspace. The protected target could be read by its authorized owner, so this
is an access check, not an unavailable-page or storage-error result.*

<a href="assets/scim-demo/new-16-web-hr-viewer.png">
  <img src="assets/scim-demo/new-16-web-hr-viewer.png" alt="Bob reads HR Workspace reference content as a W_RH_view member" width="720">
</a>

*Bob's HR content was read-only. His allowed HR read complements the separate
Demo Workspace denial; an account that cannot load any page would not be a
useful isolation test.*

<a href="assets/scim-demo/new-18-web-workspace-member-role.png">
  <img src="assets/scim-demo/new-18-web-workspace-member-role.png" alt="People settings shows Alice as Member alongside the separate setup owner" width="720">
</a>

*This full-context image was rechecked after the run: Alice is Member in the
restored baseline, alongside the setup Owner. It is not a capture of the earlier
Super_Users phase. Alice's address is reserved example.com and the setup owner's
unique identifier is hidden. Runtime checks establish the earlier phase roles.*

### Recorded Super_Users addition: source, delivery, applied state, saved edit

<a href="assets/scim-demo/new-17-entra-super-users-member.png">
  <img src="assets/scim-demo/new-17-entra-super-users-member.png" alt="Super_Users contains Alice Demo as its direct member in Entra" width="720">
</a>

*This is the source membership. Entra's Member user type is not an AppFlowy
workspace-role mapping.*

<a href="assets/scim-demo/new-20-entra-member-add-delivered.png">
  <img src="assets/scim-demo/new-20-entra-member-add-delivered.png" alt="Entra on-demand result reports Alice&#x27;s Add member operation succeeded" width="720">
</a>

*This membership addition was delivered **on demand**. The user principal name
is hidden. The operation result must be compared with AppFlowy's applied state.*

<a href="assets/scim-demo/new-21-admin-super-users-synced.png">
  <img src="assets/scim-demo/new-21-admin-super-users-synced.png" alt="AppFlowy monitor shows Super_Users and Users with one eligible member each" width="720">
</a>

*Alice belongs to both groups. Users keeps her admitted to Demo Workspace;
Super_Users supplies the explicit editor grants for General and Demo Intelligence.*

The permission checks confirmed Alice was a Demo Workspace
**Member**, with General/Demo Intelligence **Edit**, the other three spaces
**View**, no workspace-administration authority, and no HR or Executive Committee
workspace access. Bob remained an HR-only Viewer. Independent document reads and
permission checks covered the spaces, their pages and excluded workspaces. The
same active identities/emails and three-of-three seat use were retained.

<a href="assets/scim-demo/new-22-web-super-users-edit-persisted.png">
  <img src="assets/scim-demo/new-22-web-super-users-edit-persisted.png" alt="Alice&#x27;s Demo Intelligence note survives reload after Super_Users membership" width="720">
</a>

*Alice typed “Alice saved this note before moving to the HR group.” and reloaded.
The editor remained editable and the note remained visible. An independent
server read confirmed the saved note. This establishes
the reference content to compare after the next group move.*

Document writes do not prove every database operation. Test database-cell edits,
row creation/deletion and schema changes separately if those operations matter
to the deployment. The matrix's “notably on databases” description is a target,
not evidence that all database operations were exercised in this example.

## 8. Move a member without deleting the user

Use **Super_Users → HR** for the scheduled example:

1. As Alice, save a reference note in Demo Intelligence.
2. In Entra, add Alice to `HR`, then remove her from `Super_Users`. Keep `Users`.
3. Wait for a scheduled provisioning result. Do not press Provision on demand
   for this phase if the aim is to demonstrate automatic delivery.
4. In AppFlowy Admin, confirm `HR` contains Alice and `Super_Users` no longer does.
5. In Alice's already-open Web page, check whether the old permission updates.
   Then reload and check the fresh result separately.
6. Confirm Demo Intelligence is View, HR is Edit, the reference note remains,
   Alice is still the same active Member, and seat use is unchanged.

<a href="assets/scim-demo/new-23-entra-move-add-hr.png">
  <img src="assets/scim-demo/new-23-entra-move-add-hr.png" alt="Entra HR group contains Alice Demo after the target membership addition" width="720">
</a>

*Add the next legitimate assignment while keeping Users, so the move does not
remove Alice from the application's provisioning scope.*

<a href="assets/scim-demo/new-24-entra-move-remove-super-users.png">
  <img src="assets/scim-demo/new-24-entra-move-remove-super-users.png" alt="Entra Super_Users group has no members after Alice is removed" width="720">
</a>

*The source move was confirmed at **08:27:45 UTC**. These two images show the
upstream change only. Alice, HR and Super_Users were not provisioned on demand
after this move, and the Demo job was not restarted. The unrelated empty
lifecycle group is handled separately; its manual operations are labeled below.*

<a href="assets/scim-demo/new-33-admin-awaiting-upstream-move.png">
  <img src="assets/scim-demo/new-33-admin-awaiting-upstream-move.png" alt="AppFlowy still shows the previously received Super_Users membership while the upstream move waits for delivery" width="720">
</a>

*At **08:37:43 UTC**, AppFlowy still had Super_Users 1/1 and HR 0/0, while Entra
already had HR 1 and Super_Users 0. All received groups could correctly show
Synced: the new source change had not arrived yet. Refresh status does not pull
that change from Entra. Wait for the provider delivery before judging the move.*

### The scheduled move arrived without manually provisioning Alice

The next normal incremental cycle delivered the move at **08:40:06 UTC**:
Alice was removed from Super_Users and added to HR. This membership change was
not provisioned on demand, and the Demo job was not restarted. The provider's completed-cycle
result and AppFlowy's received requests established the delivery method.

<a href="assets/scim-demo/new-36-entra-scheduled-cycle-completed.png">
  <img src="assets/scim-demo/new-36-entra-scheduled-cycle-completed.png" alt="Entra reports the completed normal incremental provisioning cycle" width="720">
</a>

*The Demo application's incremental cycle completed with seven groups and one
user processed. Private identifiers are hidden. Its timing matches the received
scheduled group creation and Alice's membership change; it is not an on-demand
membership result.*

<a href="assets/scim-demo/new-35-admin-scheduled-member-move-applied.png">
  <img src="assets/scim-demo/new-35-admin-scheduled-member-move-applied.png" alt="AppFlowy applies Alice to HR, removes her from Super_Users, and retains Users" width="720">
</a>

*Compare this with the waiting screenshot above. HR now has Alice; Super_Users
is empty and Users still contains Alice. The seventh group is the separate empty
lifecycle test group, which arrived in the same scheduled cycle.*

The independent check at **08:41:24 UTC** confirmed:

- Alice can **Edit the HR space** and **View the other four Demo Workspace spaces**.
- She remains a Demo Workspace **Member**, without workspace administration.
  She still cannot access **HR Workspace** or **Executive Committee Workspace**.
- Bob remains an HR Workspace Viewer. Neither account was deleted/recreated;
  both identities and the three-of-three seat use are unchanged.
- Excluded document requests return no content. Each protected target also loads
  for the authorized setup owner, separating denial from a broken page.
- Alice's independently read saved Demo Intelligence note is unchanged.

<a href="assets/scim-demo/new-37-web-move-old-note-now-viewer.png">
  <img src="assets/scim-demo/new-37-web-move-old-note-now-viewer.png" alt="Alice&#x27;s saved Demo Intelligence note remains visible after the group move" width="720">
</a>

*This image is byte-identical to the earlier editor screenshot: it shows unchanged
content, not a visible permission difference. The separate interaction and
permission checks found the old tab stayed editable, then became read-only after
reload. The note's text describes its earlier creation, not current Edit rights.*

<a href="assets/scim-demo/new-38-web-hr-team-edit-persisted.png">
  <img src="assets/scim-demo/new-38-web-hr-team-edit-persisted.png" alt="Alice&#x27;s new HR team note remains after reload following the scheduled move" width="720">
</a>

*Alice typed “Alice can edit this HR team note after the scheduled group move.”
and reloaded. An independent saved-document read confirmed that note. Together
with the previous read-only Demo Intelligence page, this verifies the old-space
View/new-space Edit result without deleting Alice or her earlier content.*

A group move changes membership and resulting access. It does not require user
or document deletion. If the provider sends `active:false` after someone leaves
all application assignment scope, that is **workspace offboarding**, a separate
scenario below.

Repeat **HR → Product**, labeling its actual delivery method. Then test Bob
**W_RH_view → W_RH_edit → W_RH_view**. His authorized editor note should survive
the return to View.

### The next HR → Product move was delivered on demand

Alice was added to `Product` and removed from `HR`, keeping `Users`. This phase
used **Provision on demand** for those groups; it is separate from the preceding
scheduled example.

<a href="assets/scim-demo/new-42-admin-product-member-synced.png">
  <img src="assets/scim-demo/new-42-admin-product-member-synced.png" alt="AppFlowy shows Alice in Product and Users, with HR now empty" width="720">
</a>

*The applied roster follows the source move. The temporary renamed group is
still present at this point because its separate scheduled deletion has not
arrived; its presence does not grant Alice content access.*

The completed checks confirmed Product **Edit**, the other four Demo spaces
**View**, workspace **Member**, and no HR or Executive Committee workspace access.
Bob remained an HR-only Viewer. Authorized document reads and denied requests
without content matched the intended permissions; identities and seats were unchanged.

<a href="assets/scim-demo/new-43-web-product-edit-persisted.png">
  <img src="assets/scim-demo/new-43-web-product-edit-persisted.png" alt="Alice&#x27;s Product note remains after reload following the move from HR" width="720">
</a>

*Alice typed “Alice can edit Product after moving from the HR group.” and reloaded.
An independent saved-document check confirmed the note. This is the new Product
write result, not another scheduled-delivery claim.*

### Bob's HR editor and restored-viewer phases

Bob was added to `W_RH_edit` and removed from `W_RH_view`. These HR application
changes were delivered **on demand**. Independent checks confirmed Edit in both
HR spaces, workspace Member, no workspace-administration authority, and no Demo
or Executive Committee workspace access. Document reads and permission checks
matched those expectations; his identity and three-of-three seat use were unchanged.

<a href="assets/scim-demo/new-29-admin-hr-editor-synced.png">
  <img src="assets/scim-demo/new-29-admin-hr-editor-synced.png" alt="HR monitor shows W_RH_edit with Bob and W_RH_view empty during the editor phase" width="720">
</a>

*Both groups are Synced. This is the editor checkpoint, distinct from the earlier
viewer image and the later return to View.*

<a href="assets/scim-demo/new-28-web-hr-editor-persisted.png">
  <img src="assets/scim-demo/new-28-web-hr-editor-persisted.png" alt="Bob&#x27;s HR Workspace note survives reload while he is an editor" width="720">
</a>

*Bob typed “Bob saved this HR note while he was an editor. Keep this note after
he returns to viewer.” The note survived reload and was confirmed by an independent
server read. This is a saved editor write, not yet the subsequent
revocation result.*

Bob was then returned to `W_RH_view` and removed from `W_RH_edit`, again using
the HR application's on-demand flow. Independent checks confirmed his HR
Member/View baseline was restored and the other workspaces remained denied.
The already-open Web session and fresh saved-state checks are separate from that
server-permission checkpoint.

The already-open editor still accepted typing after that server permission change. The operator physically typed **“Revoked Bob edit must not
be saved.”** into the stale page.

<a href="assets/scim-demo/new-31-web-stale-editor-local-only.png">
  <img src="assets/scim-demo/new-31-web-stale-editor-local-only.png" alt="Bob&#x27;s stale editor displays a locally typed sentence after Edit was revoked" width="720">
</a>

*This is a **client limitation**: the old page still accepted local typing. The
last sentence is not evidence of a saved or authorized edit. Do not use this
stale display as the final permission result.*

Two independent owner reads confirmed the saved server document was **unchanged
by the revoked write**, retained Bob's authorized note, and did not contain the
later sentence. A fresh Bob browser session loaded a read-only document with the
original authorized note and no revoked-write sentence.

<a href="assets/scim-demo/new-30-web-restored-viewer-fresh-session.png">
  <img src="assets/scim-demo/new-30-web-restored-viewer-fresh-session.png" alt="A fresh Bob viewer session retains the authorized note but not the revoked local edit" width="720">
</a>

*This image is byte-identical to Bob's earlier editor screenshot. It shows the
authorized note retained and the revoked sentence absent; it has no visible
read-only indicator. Fresh-session input and server checks established View
access separately. No explicit rejection acknowledgement was captured.*

<a href="assets/scim-demo/new-32-web-bob-executive-access-denied.png">
  <img src="assets/scim-demo/new-32-web-bob-executive-access-denied.png" alt="The restored Bob viewer&#x27;s fresh session is denied a direct Executive Committee page link" width="720">
</a>

*This is a generic denial screen: Bob's identity and the Executive target are
not visible in its pixels. They were verified in the session and request checks.
Together with the Demo Workspace denial and authorized HR read, those checks
cover both excluded workspaces. The old stale session was then closed.*

An actual click-and-type attempt in the fresh viewer session also failed to insert “Fresh viewer edit must not be saved.” The editor remained
read-only and Bob's authorized note was still present. This checks the input
behavior as well as the displayed permission state.

**Check stale clients carefully.** Local text is not proof of a saved edit. If an
already-open editor accepts typing after a downgrade, compare an independent
fresh reader and fresh server state. Reloading the same browser may retain local
unsaved text. Report that separately from the authorization result; do not claim
an explicit server rejection unless one was actually observed.

## 9. Test workspace offboarding and administrator demotion

### Remove only Executive Committee access

Add Alice to `Codir`, verify delivery to both applications and save an Executive
Committee note. Remove her from the application scope for Executive Committee
while retaining `Users` in Demo Workspace. Confirm the actual user-offboarding
delivery, not merely a group roster change. Test both the already-open page and
a direct link in a fresh session: the removed workspace must deny content access.

The expected result is no Executive Committee membership/access, continued Demo
Workspace Member/View access, the same active account and retained authored
content visible to another authorized user. One connection's completion does
not prove the other connection has processed its separate membership update.

### Recorded Codir admission and editing

The Demo Workspace Codir membership was delivered on demand. Executive Committee
admission arrived through its normal scheduled cycle. The previous Product grant
was also removed; that removal overlapped a manual request and a normal cycle,
so its trigger is not attributed to only one of them.

<a href="assets/scim-demo/new-46-admin-executive-member-synced.png">
  <img src="assets/scim-demo/new-46-admin-executive-member-synced.png" alt="Executive Committee monitor shows Codir with one eligible synced member" width="720">
</a>

*Alice has been admitted through Codir. This is separate from the earlier empty
Codir setup checkpoint and from the later offboarding result.*

Independent checks confirmed Alice was a **Member in both workspaces**, with
**View** across Demo Workspace, **Edit** across the two Executive Committee
spaces, and **no HR Workspace access**. Neither membership granted workspace
administration. Bob's HR-only access, both identities and seat use were unchanged.

<a href="assets/scim-demo/new-45-web-executive-edit-persisted.png">
  <img src="assets/scim-demo/new-45-web-executive-edit-persisted.png" alt="Alice&#x27;s Executive Committee note remains after reload as a workspace Member" width="720">
</a>

*Alice physically typed the new note, reloaded, and an independent saved-document
read confirmed it. Editing this content does not require or grant the workspace
Owner role. This note is the reference for the offboarding retention check.*

### Recorded workspace offboarding: access removed, account and note retained

After Alice left source Codir, the Demo connection's group removal was delivered
on demand. A separate **Provision on demand for Alice's user** in the Executive
Committee application delivered that connection's `active: false` update.

<a href="assets/scim-demo/new-47-entra-workspace-offboarding.png">
  <img src="assets/scim-demo/new-47-entra-workspace-offboarding.png" alt="Entra reports a successful connection-scoped active True to False update" width="720">
</a>

*The image shows a successful active True→False update. The tested identity and
Executive application are established by the session/request records; they are
not fully visible in this detail panel. Alice's Executive SCIM record remains
present but inactive; her global account and Demo connection remain active.*

Independent checks confirmed Alice lost Executive Committee membership and
fresh document access, while remaining a Demo Workspace Member with Users/View.
Her account identity/email and seat use were unchanged. The denied Executive
responses contained no document payload. An inactive user can remain referenced
in the received SCIM group until a separate membership update arrives; that
reference does not retain effective workspace membership or access.

<a href="assets/scim-demo/new-49-web-offboarded-user-direct-link-denied.png">
  <img src="assets/scim-demo/new-49-web-offboarded-user-direct-link-denied.png" alt="A fresh Alice session cannot open the direct Executive Committee page link after offboarding" width="720">
</a>

*The generic error does not display Alice or the target workspace. Recorded
session/URL checks identify this as her fresh attempt to open the previously
editable Executive document. Her unchanged account can still use Demo Workspace.*

<a href="assets/scim-demo/new-48-web-offboarded-user-note-retained.png">
  <img src="assets/scim-demo/new-48-web-offboarded-user-note-retained.png" alt="The setup owner still reads Alice&#x27;s Executive note after she loses workspace access" width="720">
</a>

*An independent saved-document check confirmed the same authorized note was
retained. Removing Alice's workspace membership did not delete the document.*

**Open-tab limitation:** Alice's already-open Executive page did not immediately
clear its cached content or stop local typing. A revoked test sentence appeared
locally, but two independent saved-document reads found it absent and the
previously authorized note unchanged. The old tab was then closed; the fresh
session above correctly denied access. This is not instant visual revocation,
and no explicit server rejection acknowledgement was captured.

### Add and remove workspace administration

Add Alice to `Admin` and verify the Demo Workspace Owner mapping. Confirm the
instance Admin frontend remains denied and neither other workspace is granted.
Remove `Admin`, keep `Users`, and verify Member/View restoration, loss of
management authority and retained content. Do not create spaces during the
Owner phase, which could add independent ownership grants.

### Recorded Admin promotion

Alice's addition to `Admin` was delivered **on demand**. The checks confirmed
**Demo Workspace Owner**, management of its workspace and non-private Custom
spaces, and **Edit** through the five explicit space grants. HR Workspace,
Executive Committee Workspace and the instance-administration endpoint remained
denied. The recorded primary owners were unchanged; Alice kept the same active
identity and seat use stayed at three of three.

<a href="assets/scim-demo/new-50-admin-owner-group-synced.png">
  <img src="assets/scim-demo/new-50-admin-owner-group-synced.png" alt="AppFlowy shows Admin and Users each with Alice as an eligible synced member" width="720">
</a>

*Admin now applies the workspace Owner mapping. Users remains the baseline
assignment so Alice can return to Member/View when Admin is removed.*

<a href="assets/scim-demo/new-51-web-admin-workspace-owner-role.png">
  <img src="assets/scim-demo/new-51-web-admin-workspace-owner-role.png" alt="People settings shows Alice as Owner alongside the separate original setup owner" width="720">
</a>

*Alice is an ordinary account receiving the mapped Owner role; the original
workspace owner remains a separate protected account. The synthetic owner's
unique identifier is hidden. Workspace Owner does not mean instance administrator.*

<a href="assets/scim-demo/new-52-web-admin-edit-persisted.png">
  <img src="assets/scim-demo/new-52-web-admin-edit-persisted.png" alt="Alice&#x27;s Internal IT note remains after reload during the Admin phase" width="720">
</a>

*Alice typed “Alice saved this Internal IT note while assigned to Admin. Keep it
after demotion.” and reloaded. An independent saved-document read confirmed the
note. It is the reference content for the following demotion check.*

### Recorded Admin removal: Member/View and original content restored

After Alice left `Admin`, on-demand provisioning removed that grant. Independent
checks confirmed **Member**, **View across all five Demo spaces**, and no workspace
or instance administration. HR and Executive Committee workspaces remained
denied. The recorded primary owner was unchanged.

<a href="assets/scim-demo/new-54-web-demoted-workspace-member-role.png">
  <img src="assets/scim-demo/new-54-web-demoted-workspace-member-role.png" alt="People settings shows Alice returned to Member while the original setup owner remains Owner" width="720">
</a>

*Removing the mapped Admin grant restored Alice's baseline role without deleting
or recreating her account.*

<a href="assets/scim-demo/new-53-web-demoted-member-readonly-note-retained.png">
  <img src="assets/scim-demo/new-53-web-demoted-member-readonly-note-retained.png" alt="Alice&#x27;s Internal IT note remains visible after workspace-role demotion" width="720">
</a>

*The image shows retained content, with no visible read-only indicator. Separate
interaction and permission checks found the old page needed a reload, after which
it was read-only. The independently checked saved note was unchanged.*

<a href="assets/scim-demo/new-55-admin-baseline-restored.png">
  <img src="assets/scim-demo/new-55-admin-baseline-restored.png" alt="The final Demo group monitor shows Users with one member and the other five groups empty" width="720">
</a>

*This image shows the Demo connection only: Users has one eligible member and
the other five groups are empty. It does not show Bob, other connections or saved
documents.*

Independent checks confirmed Alice in Users, Bob in W_RH_view, and the nine
original projections with their original identities and memberships. All six
authored notes remained saved, with none of the revoked-write test sentences.

Before cleanup, the remaining inactive Executive SCIM roster reference was
removed on demand and the complete viewer baseline was checked again. No user
DELETE request was used during this demonstration.

## 10. Test group creation, rename and deletion

Use a separate empty group named **SCIM_Lifecycle_Demo** so the eight-group matrix
remains intact. Assign it to the Demo Workspace application.

1. Create it in Entra and confirm a new corresponding AppFlowy group appears.
   Record whether delivery was scheduled or triggered on demand.
2. Rename it to **SCIM_Lifecycle_Renamed** and confirm the new name arrives.
3. Compare stable source/SCIM/workspace group identities privately to confirm
   the rename reused the group rather than creating a duplicate.
4. Delete the temporary source group, wait for the actual SCIM deletion, and
   confirm it is absent in AppFlowy while the six regular groups remain.
5. Confirm user identities and saved documents remain unchanged.

<a href="assets/scim-demo/new-25-entra-create-temporary-group.png">
  <img src="assets/scim-demo/new-25-entra-create-temporary-group.png" alt="New Entra group form for the separate SCIM_Lifecycle_Demo group" width="720">
</a>

*This is the creation form, not proof the group was saved or delivered. The
separate lifecycle group receives no content grant and is outside the eight-group
matrix. When delivered, it temporarily makes seven Demo Workspace projections.*

<a href="assets/scim-demo/new-27-entra-lifecycle-assigned.png">
  <img src="assets/scim-demo/new-27-entra-lifecycle-assigned.png" alt="The separate SCIM_Lifecycle_Demo group is assigned to the Demo Workspace application" width="720">
</a>

*This shows an application assignment, but the application heading is outside
the capture. The recorded action targeted the Demo application; the following
AppFlowy image independently shows arrival in Demo Workspace. No content grant
or administrative mapping was added for this group.*

<a href="assets/scim-demo/new-34-admin-temporary-group-created.png">
  <img src="assets/scim-demo/new-34-admin-temporary-group-created.png" alt="The temporary lifecycle group appears as a seventh Synced Demo Workspace group" width="720">
</a>

*The normal cycle created this empty group at **08:40:04 UTC**, before the
operator's later on-demand attempt. That later attempt reported a redundant
export and caused no mutation. Group creation and Alice's move therefore have
scheduled-delivery evidence; the group has no content grants.*

The temporary group's rename was delivered **on demand**, separately from the
scheduled creation. Entra sent the display-name update, AppFlowy applied it, and
private comparisons confirmed the same source/SCIM/workspace-group identities,
no members, and all six regular Demo groups retained.

<a href="assets/scim-demo/new-39-entra-group-rename-delivered.png">
  <img src="assets/scim-demo/new-39-entra-group-rename-delivered.png" alt="Entra reports the temporary group&#x27;s displayName change to SCIM_Lifecycle_Renamed" width="720">
</a>

*This shows the name update result. The rename reused the original group; it
was not a delete-and-recreate operation.*

<a href="assets/scim-demo/new-40-admin-temporary-group-renamed.png">
  <img src="assets/scim-demo/new-40-admin-temporary-group-renamed.png" alt="AppFlowy shows the same empty group as SCIM_Lifecycle_Renamed and Synced" width="720">
</a>

*The rename has arrived. Deletion is a separate operation with its own provider
request and applied result; this screenshot does not prove it.*

<a href="assets/scim-demo/new-41-entra-temporary-source-group-deleted.png">
  <img src="assets/scim-demo/new-41-entra-temporary-source-group-deleted.png" alt="Entra no longer finds the temporary source group after its deletion" width="720">
</a>

*The temporary source group was deleted in Entra. AppFlowy's separately received
group may remain until the provider sends its deletion. A source search result
is not proof of downstream removal.*

The next ordinary Demo cycle sent the temporary group's **DELETE**, which
returned **204**. A fresh SCIM read then returned **404**, the original projected
group was absent, and the six regular Demo groups remained. No job restart or
on-demand operation targeted the deleted group.

<a href="assets/scim-demo/new-44-admin-temporary-group-deleted.png">
  <img src="assets/scim-demo/new-44-admin-temporary-group-deleted.png" alt="AppFlowy shows only the six regular Demo groups after scheduled temporary-group deletion" width="720">
</a>

*SCIM_Lifecycle_Renamed is gone. The other counts reflect the Codir admission
checkpoint: Alice is in Users and Codir, not Product. Deleting the empty temporary
group did not delete users or the regular groups. This is the downstream result
that the earlier source-only deletion screenshot could not establish.*

Removing an app assignment is not the same operation as deleting the source
group. If no deletion arrives, record that result rather than calling the group
deleted. An empty-group deletion does not prove deletion of a populated group;
member additions/removals are covered by the separate matrix scenarios.

## Verified results

The refreshed run on **October 11, 2026** completed the content, role and
synchronization scenarios below. It used the approved names throughout the
published screenshots and restored the original viewer baselines at the end.
The missing creation controls and stale Web permission display remain limitations.

### Coverage of the eight groups

These **content and administration** results combine screenshots with recorded
interaction and server checks. The images illustrate selected steps; they do
not visually prove every permission cell. The [requirement evidence index](assets/scim-demo/CAPTURE_NOTES.md#requirement-evidence-index)
separates visible evidence, runtime verification and remaining gaps.

| Group | Content and administration result | Selected screenshots |
| --- | --- | --- |
| `Admin` | Demo Owner; five named spaces Edit; other workspaces and instance administration denied. Removal restored Member/View and denied management. | Role [51](assets/scim-demo/new-51-web-admin-workspace-owner-role.png) → [54](assets/scim-demo/new-54-web-demoted-workspace-member-role.png); note [52](assets/scim-demo/new-52-web-admin-edit-persisted.png) → [53](assets/scim-demo/new-53-web-demoted-member-readonly-note-retained.png) |
| `Users` | Demo Member; five named spaces View; other workspaces denied. Actual viewer typing did not save. | Counts [08](assets/scim-demo/new-08-admin-demo-groups-synced.png); page [09](assets/scim-demo/new-09-web-users-view-general.png); denial [11](assets/scim-demo/new-11-web-alice-hr-access-denied.png) |
| `Super_Users` | Member; General/Demo Intelligence Edit, other Demo spaces View; other workspaces denied. Authored note retained after the move. | Membership [17](assets/scim-demo/new-17-entra-super-users-member.png), [21](assets/scim-demo/new-21-admin-super-users-synced.png); note [22](assets/scim-demo/new-22-web-super-users-edit-persisted.png) |
| `HR` | Member; HR space in Demo Edit, other Demo spaces View; separate HR and Executive workspaces denied. | Source [23](assets/scim-demo/new-23-entra-move-add-hr.png); applied [35](assets/scim-demo/new-35-admin-scheduled-member-move-applied.png); note [38](assets/scim-demo/new-38-web-hr-team-edit-persisted.png) |
| `Product` | Member; Product Edit, other Demo spaces View; other workspaces denied. Authored Product note retained. | Applied [42](assets/scim-demo/new-42-admin-product-member-synced.png); note [43](assets/scim-demo/new-43-web-product-edit-persisted.png) |
| `W_RH_view` | HR Member/View in both test spaces; Demo and Executive workspaces denied. | Counts [19](assets/scim-demo/new-19-admin-hr-groups-synced.png); retained note [30](assets/scim-demo/new-30-web-restored-viewer-fresh-session.png); denial [32](assets/scim-demo/new-32-web-bob-executive-access-denied.png) |
| `W_RH_edit` | HR Member/Edit in both test spaces; other workspaces denied. Return to View retained the note and fresh sessions blocked edits. | Counts [29](assets/scim-demo/new-29-admin-hr-editor-synced.png); note [28](assets/scim-demo/new-28-web-hr-editor-persisted.png); stale local edit [31](assets/scim-demo/new-31-web-stale-editor-local-only.png) |
| `Codir` | Member in Demo/Executive; Demo View, Executive Edit, HR denied. Executive offboarding retained the account, Demo access and note. | Applied [46](assets/scim-demo/new-46-admin-executive-member-synced.png); note [45](assets/scim-demo/new-45-web-executive-edit-persisted.png); offboarding [47](assets/scim-demo/new-47-entra-workspace-offboarding.png), [49](assets/scim-demo/new-49-web-offboarded-user-direct-link-denied.png) |

The before/after content images **22/37** and **28/30** are byte-identical.
They show retained content; the View/Edit transitions were established by the
separate input and permission checks, not by a visible change in these images.
Generic denial screens likewise rely on the recorded session/target checks for
identity and workspace context. Creation rules are assessed separately below.

At the final checkpoint, Alice was `Users` only and Bob was `W_RH_view` only in
the eight-group matrix. Their active identities and emails were unchanged,
licensed usage stayed at **three of three**, and the nine original group
projections and memberships were restored. All six newly authored notes retained
their saved content after moves, offboarding and demotion.

### Synchronization and negative access checks

| Check | Observed result |
| --- | --- |
| Scheduled membership change | Super_Users → HR changed Alice's old editor spaces to View and the HR space to Edit without deleting her account or saved note |
| Group lifecycle | Empty group created automatically, renamed on demand with the same identity, then deleted by a normal scheduled cycle; the six regular Demo groups remained |
| Cross-workspace access | Unauthorized direct links and independent document reads denied access; denied responses contained no document payload and the owner could read every test target |
| Fresh viewer input | Actual typing did not insert a change; independently read saved content was unchanged |
| Already-open revoked editor | Local typing remained possible after downgrade/offboarding, but two independent saved-document checks excluded the revoked sentence; a fresh session was read-only or denied as appropriate |
| Primary owners remained unchanged | SCIM promotion/demotion changed Alice's mapped role; the separate recorded primary owners stayed unchanged. This demo did not attempt to mutate a protected owner |

The run verified the described document-access and role results.
It did not establish the requested restrictions on creating spaces/workspaces,
page creation, database mutations, an overriding group deny, or automatic access
to all future spaces. See [what remains unsupported](#what-remains-unsupported).

The initial name refresh used manual provisioning. Later delivery methods are
identified in each scenario; successful manual provisioning is not presented as
a scheduled test. The first fully renamed checkpoint was the Super_Users phase,
after the initial Users-only content checks.

| Component | Recorded provenance and evidence boundary |
| --- | --- |
| AppFlowy Cloud | Server-info reports `0.19.0`, `self_hosted`; exact running binary source unverified |
| Admin frontend | Local development frontend (`vdev`); source `92eff4b` |
| AppFlowy Web | Local runtime from clean source `df5c656`; task-owned process verified |
| Delivery method | Labeled per phase; one overlapping Product removal cannot be attributed to a single trigger |
| Identities and seats | Same active accounts and actual licensed usage; identifying evidence stays private |
| Privacy | Real screenshots, reviewed before inclusion; no credentials or tenant/account identifiers |

See the [capture record](assets/scim-demo/CAPTURE_NOTES.md) for the exact timeline,
full source revisions, private-check scope and media inventory. No videos are included.

## Finish the temporary demo

Restore the viewer baseline before stopping provisioning, then pause each Entra
job, disable its AppFlowy connection and close any temporary public ingress.
Keep the groups and content if they are still needed for inspection.

In this run, Alice and Bob's baselines were restored and checked again. All
three Entra provisioning jobs were paused and the three temporary AppFlowy
connections were disabled. The older unrelated connection was already disabled
and remained unchanged.

<a href="assets/scim-demo/new-56-admin-demo-connections-disabled.png">
  <img src="assets/scim-demo/new-56-admin-demo-connections-disabled.png" alt="All three demo AppFlowy connections show Disabled after the jobs are paused" width="720">
</a>

*The target Workspace and Status columns confirm the three disabled connections.
Disabling them stops this temporary integration; it does not delete the groups,
accounts or saved demonstration notes.*

The temporary tunnel and proxy were then stopped and their ingress was verified
closed. AppFlowy Web, Admin and the backend remained healthy; the existing Web
process was retained and the backend was not reset. The eight source groups,
three target workspaces, user accounts and six authored notes were retained.

To run it again, provide a reachable HTTPS endpoint, enable the intended
connections, update/test their Entra configuration and start the jobs. A closed
temporary tunnel URL cannot be reused.

**Cancel the Entra free trial when you finish and verify renewal is disabled.**
Account cancellation is separate from stopping provisioning and is not performed
by this guide.

Continue with [SCIM operations](SCIM_OPERATIONS.md) for role precedence,
offboarding, seat recovery and token rotation, or the
[Entra setup guide](ENTRA_SCIM_AUTO_SYNC.md) for provider configuration.
