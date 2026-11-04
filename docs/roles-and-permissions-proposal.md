# Roles and permissions: overview

This branch introduces auditable roles and explicit capabilities without
replacing all legacy access checks at once. Django Groups remain persistent
roles; `RoleMetadata.key` provides a stable identifier independent of the
display name. A new custom role starts with no permissions.

Members can hold a role for multiple reasons. Manual assignments and legacy
flag synchronization record their sources so removing one source does not
remove an independently held role. Existing direct Group writes outside the
supported paths are not yet covered by provenance.

Qualifications are different from roles: an explicitly opted-in permission
bundle can grant a narrow action only while the qualification is current.
There is no automatic mapping from existing instructor or duty qualifications.
Member tags are display/audience labels, not permissions. Duty and aircraft
assignments remain contextual rather than global roles.

The branch adds selected capabilities for membership, CMS, billing, roster,
knowledge-test, and logsheet actions; role and tag selectors for mailing-list
audiences; and a session-based selected-role preview currently limited to active
superusers. Legacy role and staff checks still coexist with permissions. **Kiosk sessions can no longer manage
membership applications**, even when the account has a manager flag.

Before rollout, maintainers need to approve the role-to-capability mapping,
qualification-derived actions, and remaining endpoint-specific staff access;
settle preview GET side effects and audit retention; and compare an in-place
upgrade and recipient sets against representative tenant data. The PR's
synthetic-data migration check does not establish tenant parity.

See the [implementation guide](roles-and-permissions-design-implementation.md)
for current behavior and gaps, the
[authorization inventory](roles-and-permissions-authorization-inventory.md)
for route-level evidence, and the
[release runbook](runbooks/roles-permissions-release.md) for deployment gates.
