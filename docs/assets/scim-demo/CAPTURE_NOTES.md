# SCIM demo capture record — October 11, 2026

[Current eight-person walkthrough](../../SCIM_DEMO.md)

This historical record uses Alice, Bob and a setup owner. Its screenshots and
results describe the October 11 run, not the expanded eight-person example.

**Scenario verification and cleanup complete.** Fifty-seven reviewed screenshots
use the configured group names. The timeline below
records setup, scheduled and manual delivery, content/role checks, reproduced
stale-client limitations, and restoration of the original viewer baselines.
The complete spreadsheet is not an all-features pass.

## Approved labels and workbook

- Groups: `Admin`, `Users`, `Super_Users`, `Codir`, `HR`, `W_RH_view`,
  `W_RH_edit`, `Product`.
- Workspaces: Demo Workspace, HR Workspace, Executive Committee Workspace.
- Demo Workspace spaces: General, Demo Intelligence, Internal IT, HR, Product.
- The HR and Executive Committee workspaces each use test spaces General and
  Shared. Those spaces are separate from Demo Workspace.
- Descriptions follow the supplied matrix with the company keyword replaced by
  Demo. Private account and tenant identifiers are not publication material.

The included `scim-permission-matrix.xlsx` preserves all **80 C2:L9 cells** from
the source, including the exact Rules text. It contains the original group names
and descriptions, with the sensitive company keyword replaced by Demo. It is a
requirements workbook, not a test-results workbook. SHA-256:
`6eada7459c65403a4b155d35af2bd16c6a1c1620e3ba79772240dcf389a387ed`.

## Refreshed evidence inventory

All fifty-seven included images below passed visible-content/privacy review. Images 11 and
12 are byte-identical denial screens from different verified sessions/targets.
Pairs 22/37 and 28/30 are also byte-identical, across editor and viewer phases:
they establish displayed content retention, not a visible permission transition.
Their separate interaction/permission records establish the latter. Generic
denial images do not display the account or target; those contexts were checked
privately and are stated in captions. Final wider replacements 06/07 show the full application heading, table
headers and mapping values without the earlier clipping.

| File | Visible evidence | Boundary |
| --- | --- | --- |
| `new-01-entra-eight-groups.png` | Eight approved Security/Assigned source groups | No membership/delivery claim |
| `new-02-admin-owner-mapping.png` | Demo Workspace default Member and Admin→Owner mapping | Saved mapping inspection; workspace ID explicitly hidden; not applied user-role proof |
| `new-03-admin-connections.png` | Three scoped enabled connections, defaults Member, one Demo mapping, group counts 6/2/1 | Existing counts do not prove delivery of every renamed group; older disabled connection visible; IDs hidden; localhost is demo-only |
| `new-04-web-custom-permissions.png` | Demo Intelligence Custom, Members Edit, Everyone else in Demo Workspace View | Collective audience settings, not independent member levels |
| `new-05-entra-demo-assignments.png` | Full Demo application heading and all six assigned matrix groups | Post-run configuration recheck at 09:19:03 UTC; provisioning paused, not a new delivery event |
| `new-06-entra-user-mappings.png` | Named Demo application, userName/displayName/externalId/active mappings | Post-run configuration recheck at 09:23:11 UTC; reserved example.com expression is demo-only |
| `new-07-entra-group-mappings.png` | Named Demo application, displayName/members/externalId mappings | Post-run configuration recheck at 09:23:07 UTC; mapping configuration is not operation success |
| `new-08-admin-demo-groups-synced.png` | Six renamed Demo groups Synced; Users 1/1, other groups 0/0 | Operator-restarted full scan; not a scheduled member-move result |
| `new-09-web-users-view-general.png` | General Notes and approved Demo sidebar names visible | Alice session, read-only typing and unchanged saved state established separately, not by reference-page prose |
| `new-10-entra-hr-assignments.png` | Full HR application heading and W_RH_edit/W_RH_view assignments | Post-run configuration recheck at 09:21:09 UTC; no provisioning resumed |
| `new-11-web-alice-hr-access-denied.png` | No access screen for Alice's direct HR Workspace URL | Account/target established by matching private session evidence |
| `new-12-web-bob-demo-access-denied.png` | No access screen for Bob's direct Demo Workspace URL | Distinct case, same rendered denial screen; private session/target evidence required |
| `new-13-entra-executive-assignment.png` | Full Executive application heading and Codir assignment | Post-run configuration recheck at 09:21:21 UTC; one source Codir also assigned to Demo |
| `new-14-web-alice-executive-access-denied.png` | Alice's direct Executive Committee page link denied | Matching subject/target and readable owner control established privately |
| `new-15-web-editor-group-grants.png` | Demo Workspace/Demo Intelligence context; Admin and Super_Users as Space members, setup Space owner | Post-run configuration recheck at 09:21:41 UTC; zero group members reflects restored baseline, not the earlier editor phase |
| `new-16-web-hr-viewer.png` | HR Workspace reference document visible | Bob session, read-only state and other-workspace denial supported by separate checks |
| `new-17-entra-super-users-member.png` | Alice Demo is the direct Super_Users member | Replacement image has loaded grid; upstream membership alone is not delivery |
| `new-18-web-workspace-member-role.png` | Demo Workspace context; Alice Member alongside setup Owner | Post-run restored-baseline recheck at 09:22:08 UTC; not attributed to the earlier Super_Users phase |
| `new-19-admin-hr-groups-synced.png` | W_RH_view 1/1 eligible and W_RH_edit 0/0, both Synced | On-demand rename/viewer checkpoint, not subsequent editor-phase roster |
| `new-20-entra-member-add-delivered.png` | Alice Add member Success; principal name hidden | On-demand membership operation; applied permissions checked separately |
| `new-21-admin-super-users-synced.png` | Super_Users and Users each 1/1 eligible | Membership checkpoint before subsequent source move |
| `new-22-web-super-users-edit-persisted.png` | Demo Intelligence note containing Alice's authorized sentence | Typing/reload observed; canonical saved-state proof at 08:27:53; not yet post-move retention |
| `new-23-entra-move-add-hr.png` | Alice appears in source HR group | Upstream only; scheduled downstream delivery pending at capture |
| `new-24-entra-move-remove-super-users.png` | Source Super_Users has zero members | Upstream only; no account deletion |
| `new-25-entra-create-temporary-group.png` | SCIM_Lifecycle_Demo Security/Assigned creation form | Form is not proof of saved source group or delivered projection |
| `new-26-admin-executive-group-synced.png` | Replacement: Codir Synced, 0/0 eligible and 0 received | 08:31:55 after targeted on-demand stale-membership reconciliation; no account deletion |
| `new-27-entra-lifecycle-assigned.png` | Separate lifecycle group has an application assignment | Application heading not pictured; recorded Demo assignment corroborated by target image 34 |
| `new-28-web-hr-editor-persisted.png` | HR Workspace note containing Bob's authorized sentence | Typing/reload observed and canonical read confirms save; subsequent return to View separate |
| `new-29-admin-hr-editor-synced.png` | W_RH_edit 1/1, W_RH_view 0/0, both Synced | On-demand editor checkpoint, not final viewer roster |
| `new-30-web-restored-viewer-fresh-session.png` | Authorized HR note retained; revoked marker absent | Byte-identical to editor image 28; content evidence only, read-only/input state checked separately |
| `new-31-web-stale-editor-local-only.png` | Old Bob editor displays newly typed revoked-write sentence | Observed local client limitation; same-hash fresh server read excludes the sentence |
| `new-32-web-bob-executive-access-denied.png` | Fresh restored Bob viewer is denied a direct Executive Committee Workspace target | Matching private identity/target; HR positive read and Demo negative read establish separate boundaries |
| `new-33-admin-awaiting-upstream-move.png` | At 08:37:43 Admin still has Super_Users 1/1, HR 0/0, six groups Synced | Source is already HR 1/Super_Users 0; Synced describes received state, not undelivered upstream changes |
| `new-34-admin-temporary-group-created.png` | Empty lifecycle group applied/Synced as seventh Demo group | Received through normal scheduled POST before later redundant on-demand attempt |
| `new-35-admin-scheduled-member-move-applied.png` | HR 1/1, Super_Users 0/0, Users 1/1 after received move | Seventh group is separate lifecycle fixture; permission/identity checks independently confirmed |
| `new-36-entra-scheduled-cycle-completed.png` | Normal incremental cycle complete, seven groups and one user processed | Replacement hides full private job/tenant identifiers; timing agrees with received scheduled mutations |
| `new-37-web-move-old-note-now-viewer.png` | Authored Demo Intelligence note retained after the move | Byte-identical to editor image 22; content evidence only, permission/input state checked separately |
| `new-38-web-hr-team-edit-persisted.png` | HR Team Notes with Alice's new authorized sentence | Post-move typing/reload observed; canonical read confirms persistence; no account recreation |
| `new-39-entra-group-rename-delivered.png` | Successful displayName change to SCIM_Lifecycle_Renamed | On-demand rename, not scheduled; stable identity checked privately |
| `new-40-admin-temporary-group-renamed.png` | Renamed temporary group empty and Synced; six regular groups retained | Rename applied; deletion is a subsequent separate result |
| `new-41-entra-temporary-source-group-deleted.png` | No matching temporary group in source search after confirmed deletion | Upstream deletion only; projected group still awaited provider DELETE |
| `new-42-admin-product-member-synced.png` | Product 1/1, HR 0/0, Users 1/1; temporary renamed group still present | On-demand move applied; not proof of temporary-group deletion |
| `new-43-web-product-edit-persisted.png` | Product note with Alice's authorized sentence | Typing/reload observed; canonical read confirms save after on-demand HR→Product move |
| `new-44-admin-temporary-group-deleted.png` | Six regular Demo groups remain; renamed temporary group absent | Matching scheduled DELETE/204, fresh SCIM404 and projection-absence proof; other counts reflect Codir phase |
| `new-45-web-executive-edit-persisted.png` | Executive Committee note with Alice's authorized sentence | Typing/reload observed; canonical read confirms save as Member; offboarding retention separate |
| `new-46-admin-executive-member-synced.png` | Executive Committee Codir 1/1 eligible, Synced | Normal scheduled admission; not workspace Owner authority or later offboarding |
| `new-47-entra-workspace-offboarding.png` | Successful active True→False update | Identity/application established by test context, not fully visible in detail panel; Executive scoped deactivation checked independently |
| `new-48-web-offboarded-user-note-retained.png` | Executive note with Alice's previously authorized sentence visible | Owner session and saved-state/hash comparison establish post-offboarding retention, not Alice's continued access |
| `new-49-web-offboarded-user-direct-link-denied.png` | Generic direct-page denial screen | Fresh Alice/Executive target established by recorded session/URL checks; old cached tab did not clear immediately |
| `new-50-admin-owner-group-synced.png` | Admin and Users 1/1, regular other groups 0 | On-demand Admin membership checkpoint |
| `new-51-web-admin-workspace-owner-role.png` | Alice Owner alongside protected setup owner | Synthetic owner identifier hidden; role label accompanied by enforcement checks, not instance administration |
| `new-52-web-admin-edit-persisted.png` | Authorized Internal IT note displayed | Typing/reload and editable state observed in session; canonical read confirmed save; demotion separate |
| `new-53-web-demoted-member-readonly-note-retained.png` | Authorized Internal IT note retained after demotion/reload | No visible read-only indicator; input/permission checks established View, canonical hash unchanged |
| `new-54-web-demoted-workspace-member-role.png` | Alice Member, original setup owner Owner | Source Admin removal and strict management-denial check support the role label |
| `new-55-admin-baseline-restored.png` | Demo Users 1/1, other five Demo groups 0/0, all Synced | Other connections, Bob, all identities and six-note retention are separate runtime checks |
| `new-56-admin-demo-connections-disabled.png` | Three target workspace connections Disabled | Workspace/Status columns readable; older fourth connection already Disabled and unchanged; no ingress/health claim from this image alone |
| `new-57-entra-users-description.png` | Users overview, approved description and Assigned membership | Post-run read-only check at 09:19:17 UTC; description is not automatic employee enrollment |

### Post-run configuration rechecks

The following captures were replaced or added after cleanup to make their
application/workspace context visible. All were read-only configuration rechecks;
no live provisioning was resumed and no historical transition was recreated.

| UTC time | Capture | Rechecked state |
| --- | --- | --- |
| 09:19:03 | 05 replaced | Named Demo application and six group assignments |
| 09:19:17 | 57 added | Users description and Assigned membership; not automatic employee enrollment |
| 09:21:09 | 10 replaced | Named HR application and two group assignments |
| 09:21:21 | 13 replaced | Named Executive application and Codir assignment |
| 09:21:41 | 15 replaced | Demo Intelligence group grants; Admin/Super_Users empty in final baseline |
| 09:22:08 | 18 replaced | Demo Workspace People: Alice Member in restored baseline |
| 09:23:07 | 07 replaced | Named Demo application, full group-mapping headers and values |
| 09:23:11 | 06 replaced | Named Demo application, full user-mapping headers and values |

Image 18 establishes the final restored role only; earlier phase role claims
rely on their recorded runtime checks. Image 15's zero counts reflect the final
baseline, not a newly captured historical editor phase. Scenario images such as
22/37 and 28/30 remain the original captures with their limits stated above.

### Recorded initial setup and checks

- All eight Entra groups and descriptions now use the approved spreadsheet
  labels. All eight group descriptions were subsequently reopened and verified
  against the approved spreadsheet text. Three application names are SCIM — Demo Workspace, SCIM — HR Workspace,
  and SCIM — Executive Committee Workspace. Workspaces/spaces use the guide's names.
- Demo's six group-name updates arrived at **08:20:01–08:20:03 UTC on
  October 11, 2026**, after the operator selected **Restart provisioning**.
  Original resource identities and memberships were retained. This was a
  manually restarted full scan, not a scheduled membership-change test.
- The first Demo monitor showed Users=[Alice], with five empty regular groups.
  HR/Executive renamed-group delivery was still pending at that checkpoint;
  image 03's existing counts are not proof it had finished.
- Alice's General viewer editor was non-editable. Actual click/typing did not
  insert the canary; the canonical server document hash remained unchanged at
  **08:21:29 UTC**. Direct Alice→HR Workspace and Bob→Demo Workspace links denied
  access in their own sessions, with owner-readable targets as positive controls.
- Fresh reference content was prepared across all nine spaces. Nine broken
  default guide pages failed even for their authorized owner because their
  stored payloads were missing. After waiting five minutes and retrying, those
  disposable guide pages were moved to Trash through Web. They are excluded
  from authorization evidence; the remaining positive/negative read checks
  use owner-readable targets. No permission failure is inferred from a generic
  storage or server error.

### Full renamed setup and Super_Users checkpoint

- HR name deliveries were on demand: W_RH_view PATCH at **08:24:11 UTC**, its
  membership at **08:24:13**, and W_RH_edit name PATCH at **08:24:47**. Executive
  Codir's name update was on demand at **08:26:04**. All returned success. Do not
  label the combined initial name convergence a scheduled automatic delivery.
- The first fully renamed checkpoint was **08:26:44 UTC**, after Alice had joined
  Super_Users. All nine projections retained their original source/SCIM/projected
  IDs; counts were 6 Demo / 2 HR / 1 Executive Committee. Alice was Demo Member,
  General/Demo Intelligence Edit, other three Demo spaces View, no other workspace
  access and no workspace-admin gate. Bob stayed HR-only Member/View. All 18 actual
  document probes, 18 root-view and 24 descendant-view checks passed; accounts
  remained active with the same identities/emails and seats at 3/3.
- Alice typed the new Demo Intelligence note, then reloaded it with an editable
  editor. The fresh canonical read at **08:27:53** confirmed “Alice saved this
  note before moving to the HR group.” This is the saved reference for retention.
- The Entra source move Super_Users→HR was confirmed at **08:27:45**, with Users
  retained. No Demo restart or on-demand operation for Alice, HR or Super_Users followed the
  source move. Separate empty-group lifecycle operations do not deliver Alice's
  membership move.
  Scheduled delivery was pending at this checkpoint; images 23/24 are source
  evidence only. At **08:37:43**, image 33 still shows the old received Super_Users
  1/1 and HR 0/0 with all groups Synced. This is not a contradictory sync result:
  a Synced badge describes only the last received data, not an undelivered source
  change. No on-demand operation for Alice/HR/Super_Users or Demo job restart was
  used to accelerate the member move. Unrelated empty lifecycle operations are
  tracked separately.
- An empty extra lifecycle group was created and assigned upstream, outside the
  eight matrix groups and without content grants. An on-demand creation was
  planned, but the actual normal cycle created the group first; the later manual
  attempt was redundant. See the verified timeline below. Creation-form image 25
  and assignment image 27 are setup evidence, not by themselves delivery proof.
- Bob's source viewer→editor move began separately using the HR application's
  on-demand flow. No completed editor-phase claim is made until its result is
  recorded below.

### HR editor and return-to-View checkpoint

- Bob's W_RH_edit addition arrived on demand at **08:29:22 UTC**, followed by
  W_RH_view removal at **08:30:11**, both successful. Strict **08:30:16** checks
  passed: Edit in both HR spaces, Member/no administration, no Demo/Executive
  membership or content access, all 18 actual document and related permission
  checks, same active identity and 3/3 seats. Alice's scheduled HR move had not
  arrived yet, so her received Super_Users access was still expected at this time.
- The fresh canonical document contained Bob's new note: “Bob saved this HR note
  while he was an editor. Keep this note after he returns to viewer.” Image 28
  is after reload and is supported by that independent saved-state read.
- Codir's stale inactive received membership was reconciled separately using
  Executive application on-demand provisioning. Replacement image 26 at **08:31:55**
  shows 0 received and 0 eligible, matching its empty source group. The account
  was not deleted. The earlier 1-received screenshot is not in the publication set.
- Bob's subsequent return to W_RH_view and removal from W_RH_edit passed strict
  checks at **08:34:41**: HR Member/View restored, Demo/Executive denied, identity
  and seats unchanged. Stale-open-Web behavior and fresh saved-content comparison
  remain separate checks; do not infer their result from the restored API level.

### Revocation: stale local text versus canonical saved state

After the **08:34:41 UTC** server View checkpoint, Bob's already-open editor
remained `contenteditable=true`. At about 08:36 the operator physically typed
“Revoked Bob edit must not be saved.”; image 31 shows this local text. The fresh
owner canonical reads at **08:36:07 and 08:36:59** had an unchanged hash from
before the attempt, retained the authorized editor note and excluded the revoked
sentence. A new
isolated Bob browser context was `contenteditable=false`, retained
the authorized note and had no revoked sentence (image 30). This is a reproduced
stale-client UI limitation alongside unchanged authorized server content. It is
not proof of a captured explicit rejection acknowledgement or of instant client
revocation. The fresh Bob session also denied a direct Executive Committee
Workspace link (image 32). The old stale Bob session was closed after comparison,
preventing its unsaved local canary from affecting a later scenario. No source-code
fix is included in this documentation task. The fresh-context screenshot is
sequenced by its capture record rather than assigned an inferred exact minute.
At **08:38:36**, actual click/typing of “Fresh viewer edit must not be saved.”
failed to insert text: the fresh editor remained non-editable and the authorized
note stayed visible. This is a distinct fresh-input check after the stale-session
comparison.

### Verified scheduled move and empty-group creation

The normal Demo cycle received these mutations before the operator's subsequent
empty-group-only on-demand attempt:

| UTC time | Observed delivery |
| --- | --- |
| 08:40:04.829 | Empty lifecycle group POST returned 201 |
| 08:40:06.347 | Alice removed from Super_Users |
| 08:40:06.638 | Alice added to HR |
| Through 08:40:08.187 | Idempotent membership repeats; provider marked incremental cycle complete |
| 08:40:56 | Operator's empty-group on-demand result was SkippedRedundantExport; no subsequent mutation from that attempt |

Both group creation and the membership move therefore have scheduled evidence.
No Alice/HR/Super_Users on-demand action or Demo restart was used to trigger the
move. The later empty-group manual action must not be credited with creating it.

Strict checks at **08:41:24** passed: Alice HR space Edit, four other Demo spaces
View, Demo Member/no administration, no HR/Executive workspace access; Bob HR
Workspace View; accounts active with original identities/emails and 3/3 seats.
All actual denied document requests lacked content payload, and every target had
a successful authorized-owner read as a positive control. Seven Demo projections
included the temporary empty lifecycle group; the eight regular source groups
and their original identities remained.

Alice's authored Demo Intelligence note stayed present and byte-identical in an
independent canonical saved-state comparison. Her already-open editor was still
editable after delivery; reloading made it read-only and retained the note (image
37). This is a reproduced stale permission-UI limit, not a loss of content or an
instant open-tab refresh success. Alice then typed the HR-space note “Alice can
edit this HR team note after the scheduled group move.” and reloaded (image 38).
The independent canonical document read at **08:42:58** confirmed the saved
marker, completing the named old-space View/new-space write demonstration.

### Temporary-group rename and later scheduled deletion

The operator triggered empty-group on-demand provisioning at **08:42:31 UTC**.
The sole name mutation was a successful displayName PATCH at **08:42:36.044**.
Private checks at **08:42:58** confirmed the same source, SCIM and projected group
identities; the new name SCIM_Lifecycle_Renamed; empty membership; and all six
regular Demo groups retained. Images 39/40 pair the provider result with applied
AppFlowy state. This rename is manual on-demand evidence, unlike its earlier
scheduled creation.

The source group was deleted in Entra at **08:43:09**. No job restart was used to
force deletion. The later ordinary cycle sent **DELETE at 09:00:53.638731**, which
returned **204**. Fresh checks found SCIM **404**, the original projected group
absent, and all six regular Demo groups retained. No on-demand call targeted the
deleted group. Image 44 records the applied absence. Source screenshot 41 alone
would not prove this downstream result.

### Product move confirmed on demand

Product addition arrived at **08:44:28.302508 UTC**, followed by HR removal at
**08:45:08.236956**, both through on-demand operations and successful PATCHes.
Strict checks passed at **08:46:04**: Alice Product Edit, other four Demo spaces
View, Demo Member/no administration, no HR or Executive Committee access; Bob
HR-only Viewer. Actual document reads, denials without content, positive controls
for all nine owner-readable targets, unchanged active account identities and
3/3 seats all matched expectations. The canonical Product document contained
“Alice can edit Product after moving from the HR group.” after UI reload.
The temporary group's downstream deletion was still pending; image 42 deliberately
shows that separate retained projection rather than a false completed deletion.

### Codir admission and Executive Committee edit

- Demo Codir membership was manually provisioned at **08:46:35 UTC**.
- Executive Codir activation arrived through its **normal scheduled cycle at
  08:48:45–08:48:47**; no manual Executive operation triggered this phase.
- Product removal arrived at **09:00:50.611**, overlapping the operator's Product
  on-demand action and the ordinary Demo cycle. Delivery is confirmed, but its
  trigger is ambiguous and is not uniquely attributed to manual or scheduled work.
- Strict Codir checks passed at **09:01:05**: Alice Demo Workspace Member/View,
  Executive Committee Member/Edit in both spaces, HR denied; Bob HR-only Viewer
  among these three matrix workspaces. Original group identities and active
  account identities were retained, group counts returned to 6/2/1 after temporary
  deletion, and seats remained 3/3. The older unrelated demo workspace was not
  removed; isolation claims concern the three named target workspaces.
- Alice physically typed the Executive note at **09:01:13** and reloaded. A fresh
  canonical read as Alice at **09:01:35** confirmed the saved marker. This supplies
  the reference document for the upcoming scoped-offboarding check.
- Bob's fresh-viewer attempted marker was absent from fresh canonical content;
  his authorized note and state hash were unchanged. This supplements the
  earlier fresh-editor input check rather than inferring saved state from UI.
- Alice was removed from source Codir at **09:01:45**, with the empty source roster
  confirmed at **09:01:55**. Scoped offboarding is a subsequent phase and is not
  claimed complete at this admission checkpoint.

### Executive Committee offboarding and stale tab

- Alice's source Codir removal was confirmed by **09:01:55 UTC**. Demo group
  removal was triggered on demand at **09:02:34** and delivered at **09:02:41**.
  Executive user on-demand provisioning was triggered at **09:02:47**; its
  `active:false` update arrived at **09:02:50**, both requests successful.
- Strict offboarding checks passed at **09:03:06**. Alice's Executive membership
  was absent; fresh document reads denied with application code 1012 and no
  content payload. The Executive SCIM record remained present/inactive. Demo's
  record stayed active with Users/View, and her global UUID/email remained
  unchanged and active; seats remained 3/3. The owner's fresh Executive document
  retained the authored note with the pre-offboarding hash. The raw SCIM group
  may still reference inactive Alice until a separate membership-removal delta;
  effective projected membership/access was already absent. These are distinct
  state layers, not a retained authorization grant.
- The old Alice tab still displayed its previously loaded content and an editable
  editor. At **09:03:21**, physical typing inserted “Offboarded Alice edit must
  not be saved.” locally. Fresh independent owner reads at **09:03:34** and
  **09:04:06** excluded that canary and retained the authorized note with the
  original hash. No explicit rejection acknowledgement was observed.
- A fresh isolated Alice session denied the same Executive direct URL (image 49),
  while the authorized owner still read the note (image 48). The old stale tab
  was closed at **09:04:14** to prevent its unsaved local text affecting later
  phases. This is a documented stale cached-content/editor limitation, not an
  instant existing-tab No Access result. Subsequent Admin tests use the fresh
  Alice session.

### Admin promotion

Source Admin addition was made at **09:04:06 UTC**, on-demand provisioning at
**09:04:10**, and the membership PATCH arrived at **09:04:16.084980**, returning
200. Strict promotion checks passed at **09:04:30**: Alice Demo Workspace Owner;
workspace, space, member and sidebar management allowed; Edit through all five
explicit Custom-space member grants. HR/Executive access and instance Admin
endpoint denied. Primary recorded owners unchanged, same active identity/email,
seats 3/3.

Alice typed the Internal IT reference note at **09:04:57** and reloaded at
**09:05:22**, with editable editor and retained note (image 52). A fresh Alice
canonical GET/Yjs read at **09:05:37.276996** confirmed the exact marker “Alice saved
this Internal IT note while assigned to Admin. Keep it after demotion.”
Profile/displayName changes are outside this spreadsheet-focused rerun and are
not claimed from earlier evidence.

### Admin demotion and final baseline

Source Admin removal was confirmed at **09:05:46 UTC**; on-demand provisioning
was triggered at **09:06:15** and the removal PATCH arrived at **09:06:20.987999**,
returning 200. Strict checks passed at **09:06:34**: Alice Member/Users only,
all five Demo spaces View with can_write=false, workspace and instance
administration denied, and HR/Executive denied. Bob remained HR-only Viewer
within the three target workspaces. The nine original group identities and
initial projected memberships were restored, counts 6/2/1, identities active
and unchanged, seats 3/3. Recorded primary owners remained unchanged.

The old Alice editor was still editable at **09:06:30**. After reload at
**09:06:39**, it was non-editable and retained the Internal IT note, inspected
at **09:06:45** (image 53). People settings showed Alice Member and the original
setup owner Owner (image 54); image 55 shows the final Demo group baseline.
Fresh canonical reads of all six newly authored notes at **09:06:34–09:06:47**
matched their original authorized-write hashes after the moves, offboarding
and demotion. All revoked-write markers were absent.

### Final reconciliation before cleanup

The remaining raw Executive Codir inactive reference was cleaned up **manually**:
on-demand provisioning was clicked at **09:10:58 UTC**, and the group PATCH at
**09:11:02.851972** returned 200. The received roster then had zero members.
Effective Executive membership/access had already been removed by the earlier
scoped deactivation; this later roster cleanup was not required to establish
that security result and is not scheduled-delivery evidence.

The final ready-for-cleanup snapshot passed at **09:11:17**. Baseline permissions,
actual document access, original identities and nine groups (6/2/1), original
projected memberships, and licensed usage (3/3) matched expectations again.
All six authorized notes retained their original hashes. This final check covered
nine spaces, 18 space-level plus 18 root-view and 24 descendant-view permission
checks, 18 actual document reads (7 allowed / 11 denied without content), and
nine successful owner-read controls. The current rerun contained **zero DELETE Users requests**; workspace-scoped deactivation and
membership/role updates did not delete the global users.

## Verification scope and limits

For each phase, private evidence identifies the account, source membership,
target, received mutation, applied state, fresh Web result and independent
permission/persistence checks. Published images omit identifying values.

All eight spreadsheet content/administration rows were exercised, including the
Users baseline, Super_Users/HR/Product moves, both HR roles, Codir admission and
workspace offboarding, and Admin promotion/demotion. The final restored state
was Alice Users and Bob W_RH_view, the original nine group projections and
memberships, unchanged active identities, and three of three licensed seats.

Scheduled evidence covers the Super_Users→HR move, empty lifecycle-group creation
and deletion, and Executive Codir admission. Other phases are labeled on demand;
the overlapping Product removal is intentionally not assigned a unique trigger.
A Synced badge alone was never counted as an effective-permission check.

Negative checks used real document requests without a content payload on denial,
owner-readable positive controls, direct Web URLs, actual viewer typing,
independent saved-state comparisons and fresh isolated sessions. Already-open
revoked tabs did **not** immediately clear content or stop local typing. That
client limitation is recorded rather than marked as a successful instant
revocation; the revoked text was absent in repeat canonical checks.

A false existing-space management flag does not prove space-creation denial.
The three runtime policies allow Members and Owners to create spaces. Missing
creation-policy UI, selected-person workspace creation, database mutations,
page creation, overriding denies, populated-group deletion and automatic access
to future spaces are not passed by these document-access tests. Do not mark all
80 spreadsheet cells passed. Cleanup has its own verification record below.

## Requirement evidence index

**Visible** means the screenshot itself shows that state. **Runtime** means the
operator's session/input observation or an independent permission/document check,
recorded in the timeline above; it is not a screenshot-visible result. **Gap**
means unsupported, untested or not visually captured. No row below certifies all
80 spreadsheet cells or a production release.

### Spreadsheet content and administration columns

Columns D–L are represented below, using the group order and cell ranges from
the workbook. View/Edit results cover the named current spaces and document
fixtures; a saved text edit is not a database-operation test. Workspace access
is distinct from its Member/Owner role and from permission to create content.

| Requirement | Visible evidence | Runtime evidence | Limit or missing evidence |
| --- | --- | --- | --- |
| Admin, D2:L2 | [51](new-51-web-admin-workspace-owner-role.png) shows Owner; [54](new-54-web-demoted-workspace-member-role.png) shows Member after removal; [52](new-52-web-admin-edit-persisted.png)/[53](new-53-web-demoted-member-readonly-note-retained.png) show retained Internal IT note | Owner management gates, five spaces' Edit capabilities, other-workspace/instance-admin denials; demotion restored View and denied management | A separate saved write was not demonstrated in every space; Owner is broader than edit-only access; Private/future spaces not certified |
| Users, D3:L3 | [08](new-08-admin-demo-groups-synced.png) shows Users 1/1; [09](new-09-web-users-view-general.png) shows General content; [11](new-11-web-alice-hr-access-denied.png)/[14](new-14-web-alice-executive-access-denied.png) show denial UI | Member; five spaces View; actual General typing blocked and saved state unchanged; cross-workspace reads denied | Denial images omit account/target; General image has no explicit View badge; [57](new-57-entra-users-description.png) shows the Users description but Assigned membership is not automatic enrollment |
| Super_Users, D4:L4 | [17](new-17-entra-super-users-member.png) shows Alice in the source group; [21](new-21-admin-super-users-synced.png) shows 1/1 applied; [22](new-22-web-super-users-edit-persisted.png) shows authored note | Member; General/Demo Intelligence Edit capabilities, other Demo spaces View, other workspaces denied; Demo Intelligence write independently saved | General editing capability was checked, but its own saved edit and database mutations were not separately demonstrated |
| Codir, D5:L5 | [46](new-46-admin-executive-member-synced.png) shows 1/1 applied; [45](new-45-web-executive-edit-persisted.png) shows note; [47](new-47-entra-workspace-offboarding.png) shows active True→False; [49](new-49-web-offboarded-user-direct-link-denied.png) shows denial | Member in Demo/Executive, Demo View, Executive Edit, HR denied; scoped offboarding removed Executive access while account/Demo/note remained | Both Executive spaces checked; one authored-note fixture used for persistence. Old cached tab did not instantly clear |
| HR, D6:L6 | [23](new-23-entra-move-add-hr.png)/[24](new-24-entra-move-remove-super-users.png) show source move; [35](new-35-admin-scheduled-member-move-applied.png) shows applied counts; [38](new-38-web-hr-team-edit-persisted.png) shows HR note | Demo Member; HR space Edit, other four View; separate HR/Executive denied; old note retained and new HR write saved | [22](new-22-web-super-users-edit-persisted.png)/[37](new-37-web-move-old-note-now-viewer.png) are identical content snapshots, not visible Edit→View proof |
| W_RH_view, D7:L7 | [19](new-19-admin-hr-groups-synced.png) shows initial viewer membership; [30](new-30-web-restored-viewer-fresh-session.png) shows retained HR note; [12](new-12-web-bob-demo-access-denied.png)/[32](new-32-web-bob-executive-access-denied.png) show denial UI | HR Member/View in two spaces, Demo/Executive denied; fresh-session actual typing blocked and server state unchanged | Final restored source/group-monitor screenshots were not captured; image 19 is the earlier baseline, image 30 has no explicit View badge |
| W_RH_edit, D8:L8 | [29](new-29-admin-hr-editor-synced.png) shows editor 1/1 and viewer 0/0; [28](new-28-web-hr-editor-persisted.png) shows authorized note; [31](new-31-web-stale-editor-local-only.png) shows later local canary | HR Member/Edit in two spaces, other workspaces denied; authorized write saved; return to View retained it and revoked text did not persist | Source-side Bob membership changes have no dedicated image; [28](new-28-web-hr-editor-persisted.png)/[30](new-30-web-restored-viewer-fresh-session.png) are identical content snapshots; instant stale-client refresh failed |
| Product, D9:L9 | [42](new-42-admin-product-member-synced.png) shows Product 1/1 and HR 0/0; [43](new-43-web-product-edit-persisted.png) shows Product note | Demo Member; Product Edit, other four View, other workspaces denied; actual Product write saved, identity retained | Source-side Product move has no dedicated roster image; later Product removal overlapped manual and scheduled work, so trigger is not isolated |

### Creation rules and broader permission requirements

| Requirement | Evidence or outcome | Status |
| --- | --- | --- |
| C2: Admin may create workspaces, spaces and pages | Role mapping and management checked; creation actions not exercised. Selected-person whole-workspace creation is a separate requested policy | **Not fully verified**; selected-person controls require implementation |
| C3:C7 and C9: with Edit, create pages but not spaces | All three runtime policies allowed Members and Owners to create spaces. Existing-page edits do not prove page creation or sidebar policy | **Not satisfied as a complete UI configuration**; creation controls missing; page creation untested |
| C8: W_RH_edit may create spaces and pages | Runtime policy allows Members to create spaces; no actual space/page creation test was run | **Not verified by this demo** |
| Different ordinary group View/Edit permissions with everyone else denied | [04](new-04-web-custom-permissions.png) shows collective Space Members Edit / Everyone Else View; [15](new-15-web-editor-group-grants.png) shows group grants | **Unsupported strict allowlist combination**; documented recipe intentionally lets other admitted workspace members view |
| Existing and future-space policy | Nine current spaces inspected; explicit grants used | **Not certified** for all future spaces or exceptions |
| Overriding No Access despite another grant | For this demo only, interpreted as absence of a grant; requester has not confirmed additive versus overriding-deny intent | **Not implemented/tested** by this example |
| Immediate access removal in open clients | [31](new-31-web-stale-editor-local-only.png) shows revoked local typing; independent saved reads excluded it; fresh sessions were read-only/denied | **Observed client limitation**; not an instant revocation pass |
| Database edits, rows and schema | Text-document writes only; “notably on databases” remains a workbook requirement | **Untested** |

### SCIM lifecycle, identity, and operational requirements

| Requirement | Visible evidence | Runtime evidence and boundary |
| --- | --- | --- |
| Group creation | [25](new-25-entra-create-temporary-group.png) form, [27](new-27-entra-lifecycle-assigned.png) assignment, [34](new-34-admin-temporary-group-created.png) target seventh group | Scheduled POST201 preceded redundant on-demand attempt; image 27 lacks app heading, target 34 supplies workspace context |
| Group rename | [39](new-39-entra-group-rename-delivered.png) successful old→new displayName; [40](new-40-admin-temporary-group-renamed.png) applied name | On-demand PATCH; stable source/SCIM/projected identities checked privately; screenshot names alone do not prove stable identity |
| Group deletion | [41](new-41-entra-temporary-source-group-deleted.png) source absence; [44](new-44-admin-temporary-group-deleted.png) target absence | Normal scheduled DELETE204, SCIM404 and projection absence confirmed; only an empty group's deletion was tested |
| Member addition/removal and scheduled move | [17](new-17-entra-super-users-member.png), [23](new-23-entra-move-add-hr.png), [24](new-24-entra-move-remove-super-users.png), [33](new-33-admin-awaiting-upstream-move.png), [35](new-35-admin-scheduled-member-move-applied.png), [36](new-36-entra-scheduled-cycle-completed.png) | Source, waiting target and applied target distinguished; received mutation timeline establishes scheduled delivery, not a Synced badge alone |
| No user deletion when moving groups | Content retained in [22](new-22-web-super-users-edit-persisted.png)/[37](new-37-web-move-old-note-now-viewer.png) and later notes | Same global identity/email, zero DELETE Users calls and unchanged active accounts checked privately; no screenshot alone proves global identity retention |
| Workspace-only offboarding | [47](new-47-entra-workspace-offboarding.png), retained content [48](new-48-web-offboarded-user-note-retained.png), fresh denial [49](new-49-web-offboarded-user-direct-link-denied.png) | Executive scoped active=false, effective membership removed, Demo remained active, owner retained note; raw inactive group reference was cleaned separately |
| Role mapping and primary-owner stability | [02](new-02-admin-owner-mapping.png), Owner [51](new-51-web-admin-workspace-owner-role.png), Member [54](new-54-web-demoted-workspace-member-role.png) | Mapped role changed only ordinary Alice; primary owner identities unchanged and instance admin denied. No protected-owner mutation was attempted; Entra app role User is not an AppFlowy role |
| Actual unauthorized access | [11](new-11-web-alice-hr-access-denied.png), [12](new-12-web-bob-demo-access-denied.png), [14](new-14-web-alice-executive-access-denied.png), [32](new-32-web-bob-executive-access-denied.png), [49](new-49-web-offboarded-user-direct-link-denied.png) | Generic screens omit subject/target; session/URL identities and fresh document denials without content verified, each with an owner-readable positive control |
| Seat usage and license recovery | No public license-state screenshot in this run | Three-of-three seats remained stable; fourth-user license failure, license increase and automatic retry were **not tested in this rerun** |
| Profile/email modification and AD | No corresponding screenshot | User-profile changes, login-email changes and on-premises AD/nested-group behavior **not tested**; this is cloud Entra group provisioning |
| Cleanup | [56](new-56-admin-demo-connections-disabled.png) shows three target connections Disabled | Jobs paused, scoped token401, task-owned ingress closed, local health200 verified; trial cancellation remains the user's action |

The image audit found no mismatched group counts or sensitive values in these
historical scenario captures. Their evidentiary limits are retained above rather
than rewriting history or adding synthetic permission indicators.

## Runtime provenance

| Component | Observed provenance |
| --- | --- |
| Cloud | Health and server-info HTTP 200 at 08:10 UTC; reports `0.19.0`, `self_hosted`; exact running binary source remains unverified |
| Admin | SCIM settings HTTP 200; checkout `92eff4b1138b448b534c93442a9237f4eb7b4af5`, UI `vdev`; no tracked source changes at 08:23:31; exact process-to-source provenance not independently established |
| Web | Port 3006 HTTP 200; source `df5c65699fd408e1f0522fbe16a35943fefe6f35`; clean checkout and matching task-owned process/start-command fingerprint verified at 08:23:31 UTC |
| Capture date | October 11, 2026 |
| Initial identity/role/content check | 08:20:45 UTC; source group-name delivery still pending for HR/Executive at this checkpoint |

The 08:20:45 strict check confirmed unchanged active Alice/Bob identities/emails,
3/3 seats, all nine Custom policies, Alice Demo Workspace Member, Bob HR Workspace
Member, neither in Executive Committee Workspace, owner-gated administration
results and root/descendant permission results. Eighteen actual document GET
probes produced seven allowed and eleven denied results. The requested-write
flags were false for both baseline Viewers. A decoded General document read
at 08:22:12 separately found no canary. These baseline content checks do not
prove that the two pending connections had received every renamed source group.

Record Cloud's reported version and deployment mode, exact running source build
if established, Admin source/build and Web source/build. A source checkout alone
does not prove the running backend binary came from it. Do not label this a
release-version validation without that evidence.

## Capture and privacy rules

- Capture real application/portal state. Do not generate or alter labels,
  permissions, success indicators or counts to make a screenshot match the guide.
- Use the approved group/workspace names and synthetic people/content. Keep the
  sensitive company keyword, credentials, tenant/object IDs, identifying domains,
  account headers and unrelated tabs/windows out of published media.
- Review visible pixels and metadata before including an image. A clean DOM text
  snapshot alone does not establish screenshot privacy.
- If a loopback or reserved example.com address is visible, identify it as demo
  context; it is not the public endpoint required by Entra.
- Capture provider completion and applied AppFlowy state separately. A Synced
  badge alone is not an effective-permission test.
- Distinguish scheduled delivery from Provision on demand. Do not infer a
  scheduled result from successful manual delivery.
- Show unauthorized users opening direct URLs, not only hidden navigation.
  For revocation, compare the already-open session and a fresh session.
- Check stale edits against independently read saved content. Do not infer
  persistence from local text or claim an explicit rejection acknowledgement
  without observing it.
- Missing creation-policy UI remains a limitation. Diagnostic API calls are not
  a customer UI workflow.
- No videos. Keep credentials, diagnostic logs and rejected images outside the
  repository; include only reviewed final publication assets.

## Cleanup and trial status

Demo and HR provisioning jobs were paused at **09:07:40 UTC**. Executive
provisioning was paused at **09:11:37**, after the final manual roster cleanup.
All three demo AppFlowy connections were verified Disabled at **09:11:37**.
The older unrelated connection remained Disabled and was not changed.

Infrastructure cleanup completed at **09:12:47 UTC**. Fresh API checks confirmed
all three demo connections Disabled and their scoped SCIM tokens returned 401.
The task-owned monitor, tunnel and proxy were stopped after checking their
process fingerprints; the local proxy port was closed and the former public
tunnel returned 530. No public endpoint or token value is published here.

Web, Admin and backend health checks returned 200. The original Web process was
retained and the backend was not reset. The eight matrix groups, workspaces,
user accounts and six authored notes remain available for inspection. Trial cancellation is the user's account action and has not been
performed. The user should cancel the free trial and verify renewal is disabled
when finished with the demo.
