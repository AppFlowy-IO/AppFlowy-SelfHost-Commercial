# Automatic group sync with SCIM

Manage your team in Authentik and let SCIM keep its AppFlowy group up to date. This
walkthrough shows how to connect the two systems, add and remove group members, and
use the synchronized group to grant access to a space.

The example uses **Engineering — SCIM Demo**, with two directory users, **Alice Chen**
and **Bob Rivera**. You will see the AppFlowy group change from **0 → 1 → 2 → 1 members**
without manually editing its membership in AppFlowy.

## In this guide

1. [Create the AppFlowy connection and auth key](#step-1-create-the-appflowy-connection-and-auth-key)
2. [Prepare the directory users and group](#step-2-prepare-the-directory-users-and-group)
3. [Connect Authentik to AppFlowy](#step-3-connect-authentik-to-appflowy)
4. [Check the initial group in AppFlowy](#step-4-check-the-initial-group-in-appflowy)
5. [Add Alice, then Bob](#step-5-add-alice-then-bob)
6. [Remove Alice from the group](#step-6-remove-alice-from-the-group)
7. [Give the group access to a space](#step-7-give-the-group-access-to-a-space)

For endpoint routing, other identity providers, token rotation, and the SCIM API,
see the [SCIM provisioning reference](SCIM.md).

## What happens automatically?

**Authentik group membership → SCIM update → AppFlowy workspace group membership**

Saving a membership change in Authentik queues a SCIM update. AppFlowy receives it
and processes the corresponding workspace-group membership in the background.
You manage the group's name and members in the directory; AppFlowy owns the
permissions you assign to that group.

| Item | What it controls | Who configures it? |
| --- | --- | --- |
| SCIM connection | Which AppFlowy workspace receives directory users and groups | AppFlowy administrator, once |
| Directory group | Who belongs to Engineering | Directory administrator in Authentik |
| AppFlowy workspace group | The synchronized group available in **People → Groups** | Created and maintained by SCIM |
| Space grant | What the group can do in a particular space | Workspace or space owner, once per space |

**A group is not a space.** SCIM creates the matching workspace group. It does not
create a new space. Assign that group to an existing space in step 7.

## Before you begin

- Complete the [SCIM prerequisites](SCIM.md#before-you-begin), including an enabled
  self-hosted plan, a reachable HTTPS SCIM endpoint, and enough licensed seats for
  the test users.
- Have administrator access to AppFlowy Admin and Authentik, and owner access to the
  AppFlowy workspace used for the demonstration.
- Use a dedicated workspace, such as **SCIM Sync Demo**, and test identities rather
  than the system administrator or workspace owner. Neither owner identity should
  be assigned for SCIM provisioning.
- Use Authentik **2026.5.6 or later** for the group-removal behavior shown here.
  The recordings use 2026.5.6.

> The screenshots and videos use a local development installation. Replace its
> `localhost` URLs with your own HTTPS hostname. The local Docker address
> `host.docker.internal` is shown only to explain the recording's setup.

Videos have captions and no audio. Select a video preview or its **Watch video**
link to open the MP4. If your Markdown viewer does not play it, download and open
the file. All screenshots, videos, and transcripts are stored with this guide.

## Step 1: Create the AppFlowy connection and auth key

1. In AppFlowy Web, choose or create the workspace **SCIM Sync Demo**.
2. Open the Admin frontend at `https://your-domain/console` and sign in as an
   administrator.
3. Open **Authentication → SCIM Provisioning** and select **Add connection**.
4. Complete the form with these values:

   | Field | Example value |
   | --- | --- |
   | Name | `Authentik — SCIM Demo` |
   | Workspace | `SCIM Sync Demo` |
   | Default role | **Member** |
   | Group role mappings | Leave empty |

5. Select **Create connection**. Copy the **Secret token** from the token dialog and
   store it securely for step 3. This is the auth key Authentik will use.
6. Copy the **Tenant URL**, normally `https://your-domain/scim/v2`, and confirm the
   connection appears as **Enabled**.

![AppFlowy Admin showing an enabled SCIM connection for SCIM Sync Demo, with default role Member and no role mappings](assets/scim-auto-sync/01-admin-connection.png)

**Expected result:** one enabled connection targeting the correct workspace.
The screenshot shows the completed setup; the secret token is not included in
the media.

> The token is displayed once. If you lose or rotate it, update Authentik with the
> replacement. See [Managing connections](SCIM.md#managing-connections).

**Why no role mappings?** Role mappings choose workspace roles such as Member or
Guest. They are separate from group membership and space access. A SCIM group
becomes an AppFlowy workspace group even when this table is empty.

## Step 2: Prepare the directory users and group

1. In Authentik, open **Directory → Users** and create two active test users. Set
   their usernames to their email addresses, as required by AppFlowy's SCIM mapping.

   | Display name | Username and email used in the recording |
   | --- | --- |
   | Alice Chen | `demo.alice@example.com` |
   | Bob Rivera | `demo.bob@example.com` |

2. Open **Directory → Groups** and create **Engineering — SCIM Demo**.
3. Leave the group empty for now. You will add the users while watching the sync.

These are demonstration addresses. Use test addresses appropriate for your own
installation. The users do not need to sign in for their group membership to sync.
SCIM provisioning and [user sign-in](SCIM.md#sign-in-for-provisioned-users) are
separate operations.

## Step 3: Connect Authentik to AppFlowy

### Select the users before enabling provisioning

1. Under **Applications → Applications**, create or open an application named
   **AppFlowy SCIM Sync Demo**.
2. In that application's **Policy / Group / User Bindings**, bind Alice and Bob
   directly to the application.

Keep these user assignments independent of the Engineering group. This lets you
demonstrate removing Alice from Engineering while she remains provisioned in the
workspace. Application bindings select users; the provider's group filters select
groups. A group filter alone does not restrict which users are provisioned.

### Configure the SCIM provider

1. Open **Applications → Providers**, select **New Provider**, and choose **SCIM**.
2. Configure the provider using the values below.

   | Setting | Value |
   | --- | --- |
   | Name | A recognizable name, such as `appflowy-scim-demo` |
   | URL | The AppFlowy Tenant URL, including `/scim/v2` |
   | Authentication mode | **Static token** |
   | Token | The secret token copied from AppFlowy |
   | User property mappings | Authentik's standard SCIM User mapping |
   | Group property mappings | Authentik's standard SCIM Group mapping |
   | Group filters | **Engineering — SCIM Demo** |
   | Exclude service accounts | Enabled |
   | Dry-run | Disabled |

3. Edit the application, add this provider to **Backchannel Providers**, and save.
   Authentik documents these controls in its
   [SCIM provider setup](https://docs.goauthentik.io/add-secure-apps/providers/scim/create-scim-provider/).
4. Open the provider's overview and check provisioning status and task results.
   Let initial provisioning finish. If existing objects have not been sent, use
   the initial sync described in the [Authentik setup reference](SCIM.md#authentik).

![Authentik SCIM provider overview showing the assigned application, SCIM endpoint, dry-run disabled, and successful sync status](assets/scim-auto-sync/03-authentik-provider.png)

The local recording uses `http://host.docker.internal:8000/scim/v2` because
Authentik runs inside Docker and AppFlowy runs on the Mac. Your provider must use
your installation's reachable HTTPS endpoint and trust its certificate.

**Expected result:** both users and the empty Engineering group are provisioned.
For the remaining membership steps, save changes in Authentik and let automatic
sync run; do not start a manual full sync.

## Step 4: Check the initial group in AppFlowy

1. Open **SCIM Sync Demo** in AppFlowy Web.
2. Open the workspace menu → **Settings → People → Groups**.
3. Find **Engineering — SCIM Demo** with **0 members**.

![AppFlowy People Groups tab showing Engineering — SCIM Demo with zero members](assets/scim-auto-sync/02-appflowy-empty-group.png)

**Expected result:** the group already exists in AppFlowy. You did not need to
select **Create a group** there. The member-change videos start from this state,
after initial provisioning has completed.

## Step 5: Add Alice, then Bob

### Add the first member

1. In Authentik, open **Directory → Groups → Engineering — SCIM Demo → Users**.
2. Select **Add Existing User**, open the user selector, and select Alice.
3. Select **Confirm**, then **Assign** to save the membership.
4. Refresh the Authentik table if necessary to see Alice in the group.

![Authentik Engineering group listing Alice Chen after she was assigned](assets/scim-auto-sync/04-directory-alice.png)

5. Return to AppFlowy. Reopen **People → Groups** and open Engineering using the
   pencil icon next to its name.
6. Check that the group has **1 member**, `demo.alice@example.com`.

![AppFlowy managed Engineering group listing Alice as its only member](assets/scim-auto-sync/05-appflowy-alice.png)

> **Reload the view, not the sync.** In the recorded Web version, the People screen
> keeps its loaded list. Close the group dialog, select **Profile**, then return to
> **People → Groups** to read the latest state. This does not trigger SCIM.
> The directory change triggers the background update. Authentik's table
> **Refresh** button likewise reloads its view.

### Add the second member

7. Repeat the Authentik assignment with Bob.
8. Reopen the group list in AppFlowy and check that Engineering now contains
   **Alice and Bob**.

![AppFlowy Engineering group listing Alice and Bob, with a count of two members](assets/scim-auto-sync/06-appflowy-two-members.png)

**Expected result:** membership changes from **0 → 1 → 2**. AppFlowy may display the
users' email addresses instead of their Authentik display names. The SCIM-managed
roster is read-only in AppFlowy; manage it in the directory.

### Watch the complete addition flow

[![Watch video 1: add Alice and Bob through automatic SCIM sync](assets/scim-auto-sync/06-appflowy-two-members.png)](assets/scim-auto-sync/add-members.mp4)

[**Watch video 1 — Add members automatically**](assets/scim-auto-sync/add-members.mp4)
· 1 min 43 sec · [Text transcript](assets/scim-auto-sync/add-members-transcript.txt)

The recording includes both Authentik assignments and the matching AppFlowy
results. No manual full-sync action is used.

## Step 6: Remove Alice from the group

1. In the Authentik group's **Users** tab, select Alice.
2. Select **Remove** and confirm the group-membership removal. In Authentik 2026.5.6,
   the confirmation button says **Delete**, while the dialog describes removing
   the selected user **from Engineering — SCIM Demo**.

![Authentik confirmation dialog asking to remove Alice from Engineering, with a Delete confirmation button](assets/scim-auto-sync/07-remove-from-directory-group.png)

3. Check that the Authentik group now contains only Bob. Refresh its table if needed.

![Authentik Engineering group showing Bob Rivera as its only member](assets/scim-auto-sync/08-directory-bob-only.png)

4. Return to AppFlowy and reopen **People → Groups**.
5. Open Engineering. Its count is **1 member**, and Bob is the only listed member.

![AppFlowy Engineering group showing Bob as its only member after Alice was removed](assets/scim-auto-sync/09-appflowy-bob-only.png)

**Expected result:** the group changes from **2 → 1 members** automatically.
Alice remains a workspace Member because she is still assigned to the Authentik
application and the connection's default role is Member. This action removes
group membership; it does not delete her account or deprovision her from the
workspace.

[![Watch video 2: remove Alice from the directory group and see Bob remain in AppFlowy](assets/scim-auto-sync/09-appflowy-bob-only.png)](assets/scim-auto-sync/remove-member.mp4)

[**Watch video 2 — Remove a member automatically**](assets/scim-auto-sync/remove-member.mp4)
· 35 sec · [Text transcript](assets/scim-auto-sync/remove-member-transcript.txt)

## Step 7: Give the group access to a space

Group sync and space permissions are separate. An owner assigns the group to a
space once; subsequent membership changes determine who receives access through
that group.

1. In the demo workspace, choose a space called **Engineering Hub**, or create a
   space for this example.
2. Open its **••• menu → Manage Space**.
3. On **General**, select **Custom** and configure:

   | Setting | Value for this example |
   | --- | --- |
   | Space members | **Can edit** |
   | Everyone else in the workspace | **No access** |

![Engineering Hub Custom space settings with Can edit for space members and No access for everyone else](assets/scim-auto-sync/10-custom-space-access.png)

4. Open **Members**. For an example where access comes only from the group, remove
   any existing direct space-member grants for Alice and Bob. Keep the space owner.
   Converting a Public space to Custom retains its current members, so review this
   list after conversion.
5. Select **Add people or groups**, search for Engineering, and add
   **Engineering — SCIM Demo**.

![AppFlowy space-member search showing Engineering — SCIM Demo as a group available to add](assets/scim-auto-sync/11-add-group-to-space.png)

6. Confirm that Engineering appears with the role **Space member**.

![Engineering — SCIM Demo listed as a Space member in Engineering Hub, alongside the workspace owner](assets/scim-auto-sync/12-space-group-assigned.png)

**Expected result:** Engineering is assigned to the space. Its current member,
Bob, receives the group's space-member access. You can now repeat the add/remove
exercise without reassigning the group to the space.

> A person can have more than one access path. Removing them from Engineering
> removes this group's access path. A direct grant, another group, an owner role,
> or broader space settings may still give them access.

[![Watch video 3: assign the synchronized Engineering group to a Custom space](assets/scim-auto-sync/12-space-group-assigned.png)](assets/scim-auto-sync/space-access.mp4)

[**Watch video 3 — Assign the synced group to a space**](assets/scim-auto-sync/space-access.mp4)
· 32 sec · [Text transcript](assets/scim-auto-sync/space-access-transcript.txt)

This clip starts with the Custom space configured and its direct test-user grants
removed. It demonstrates adding the group; it does not show a separate login as Bob.

## Check your result

| Checkpoint | Expected result in AppFlowy |
| --- | --- |
| Initial provisioning | Engineering group exists with 0 members |
| Alice assigned in Authentik | Engineering contains Alice |
| Bob assigned in Authentik | Engineering contains Alice and Bob |
| Alice removed from Engineering | Engineering contains only Bob; Alice remains a workspace Member in this example |
| Engineering assigned to Engineering Hub | The group appears as a Space member |

## Troubleshooting

| What you see | What to check |
| --- | --- |
| No SCIM entry in Admin | Check the [self-hosted plan prerequisites](SCIM.md#before-you-begin). |
| No group appears | Confirm the target workspace, enabled connection, reachable SCIM URL, valid token, Authentik group filter, and successful initial provisioning. |
| Group exists, but a member is missing | Confirm the user is assigned to the Authentik application, active, and an AppFlowy workspace Member or Owner. Guests and inactive users are not projected into these permission groups. Check licensed seats and provider task errors. |
| The old member count remains on screen | Allow the background tasks to finish, then reopen **People → Groups**. A fixed sync delay is not guaranteed. |
| Directory changes never arrive | Check the Authentik worker and provider task results, then AppFlowy logs. An enabled connection row indicates configuration status, not the success of the latest sync. |
| Sync stopped after token rotation | Replace the token in the existing Authentik provider. Do not recreate the provider just to change its token. |
| A removed group member can still access the space | Look for direct grants, another group, owner access, or broader space permissions. |
| You cannot edit the synchronized roster in AppFlowy | This is expected. Make the membership change in Authentik. |

For protocol errors, connection tests, and lifecycle behavior, continue with
[SCIM verification](SCIM.md#verify-the-setup) and
[Authentik's SCIM documentation](https://docs.goauthentik.io/add-secure-apps/providers/scim/).

## About the recordings

Recorded on **October 9, 2026** using the local AppFlowy Admin frontend, AppFlowy
Web, and Authentik **2026.5.6**. Initial provisioning was completed before the
membership videos. The add/remove recordings use normal Authentik UI changes,
without a manual full-sync action or direct AppFlowy membership edits.

The displayed member sets and the final space grant were checked against stored
active memberships and permissions. The local hosted development workspace used
a paid-plan test fixture to allow multiple members; this is not a self-hosted
license-validation test or a production latency measurement. Follow the licensed
self-hosted prerequisites above for your deployment. User sign-in is outside the
recording's scope.

The media contains demonstration identities and no SCIM auth key. All twelve
screenshots, three MP4 videos, and their transcripts are in
[`assets/scim-auto-sync/`](assets/scim-auto-sync/).
