# Proposal: Configurable Roles and Permissions

## What this would provide

Administrators could manage roles and their permissions in Django admin, assign roles to members, and use those roles to control application access, mailing lists, and notifications.

The system would build on Django's existing Groups and Permissions rather than introduce a separate permissions system.

## How it would work

### Terms and effects

- **Role:** A persistent member grouping represented by a Django Group. A role
  can grant application permissions and provide profile tags. New custom roles
  start with no permissions; administrators must grant them explicitly.
- **Qualification:** An awarded or recorded status with its own validity and
  revocation lifecycle. A qualification can provide permissions or operational
  eligibility and can provide profile tags. Qualification-derived permissions
  stop when the qualification expires or is revoked.
- **Member tag:** A profile display label. It may be provided by a role or
  qualification, but the tag itself is presentation only and does not grant
  access.
- **Operational assignment:** A contextual responsibility, such as a duty on a
  particular date or an assignment for an aircraft or event. It remains
  separate from persistent roles; authorization can consider the assignment
  within its context.
- **Authorization policy:** The rule for allowing an action. Depending on the
  action, it may combine a role permission, a valid qualification, an
  operational assignment, active membership, ownership, or other context.

Roles and qualifications can both provide permissions and profile tags, but
their grants have different sources and lifecycles. A Tow Pilot qualification,
for example, may provide a visible Tow Pilot tag and tow-related eligibility
while valid. A Treasurer role may provide a Treasurer tag and finance
permissions until the role is removed. Neither display tag grants access by
itself.

### Roles

A role is a Django Group with additional metadata:

```text
Role: Instructor Admins
Key: instructor_admins
Permissions: current Instructor Admins permissions
Mailing-list eligible: yes
```

The key remains stable if the display name changes. Django permissions remain attached to the Group.

Current built-in roles and permissions would be the starting defaults. Platform Administrators could create custom roles and customize protected built-in roles.

### Assigning roles

Roles could be assigned in three ways:

- **Membership status** grants or removes configured baseline roles.
- **Qualifications** can provide permissions, eligibility, and profile tags while valid. They do not have to become administrative roles.
- **Administrators** manually assign administrative or custom roles.

Automatic updates would not remove manually assigned roles. Role changes would take effect immediately and be audited.

### What administrators would see

In Django admin, authorized Platform Administrators could:

- Create a role and give it a name and description.
- Select its Django and business-action permissions.
- Choose whether it can be assigned automatically or used for mailing lists.
- Assign it to members.
- See members' roles and effective permissions.

Members could see their assigned role names and qualification-derived profile tags.

### Mailing lists and notifications

Mailing-list configuration could include eligible custom roles—for example, adding a `Weekend Coordinator` role to a list.

Notifications would be configured separately from permissions. Administrators could select which roles receive each notification topic, such as membership applications or roster updates. Existing recipient behavior would be the initial default.

### Testing access

Platform Administrators could temporarily preview the site as a selected role. The preview would be session-based, clearly indicated, and read-only; it would not change the administrator's real roles.

## Initial scope

- Preserve current built-in roles and effective permissions.
- Keep existing role fields during transition, then retire their authorization use through a defined process.
- Migrate CMS role-based page restrictions while keeping individual page-editor grants separate.
- Keep roles local to each club's deployment and database.
- Do not initially add role hierarchy, expiring assignments, or delegation.
- Implement and evaluate the changes on test deployments.

## Feedback requested

Does this product direction fit the project? The detailed design and implementation
context is in [`roles-and-permissions-design-implementation.md`](roles-and-permissions-design-implementation.md).
