"""
Data migration: create all role-based Groups and seed their canonical permissions.

This migration documents and bootstraps the 6 groups that drive Django admin
access in Manage2Soar.  It is idempotent – groups are created with
get_or_create and permissions are added with .add() – so it is safe to run
against a database that has already been partially configured via the old
loaddata/groups_and_permissions.json fixture.

Groups and their responsibility:
  - Instructor Admins  : manage the training syllabus (instructors app) and
                         knowledge-test question bank / written tests
                         (knowledgetest app).
  - Webmasters         : full access to the CMS (pages, documents, feedback,
                         visitor contacts) and siteconfig administration.
  - Member Managers    : manage member records, biographies, badges; handle
                         visiting-pilot registrations and site feedback.
  - Rostermeisters     : full access to the duty-roster scheduling system.
  - Secretary          : group created so _sync_groups can assign members;
                         admin access is controlled via Member.secretary checks
                         in admin/view code rather than model-level permissions.
  - Treasurer          : same pattern as Secretary.

Fresh-install note
------------------
If a referenced content type doesn't exist yet (the app that defines it
hasn't been migrated in this run) the permission look-up is silently skipped.
Each app is responsible for ensuring its own permissions are granted via its
own migrations (e.g. knowledgetest 0005).

Historical note
---------------
The old loaddata/groups_and_permissions.json fixture used raw PKs that were
only valid for the original production database instance.  This migration
replaces the need to load that fixture on new deployments.  The fixture also
referenced duty_roster.DutyDay and duty_roster.DutySlot which were removed in
duty_roster migration 0003; those permissions are intentionally absent here.
"""

from django.db import migrations

# ---------------------------------------------------------------------------
# Canonical permission sets (app_label, model_name, codename)
# ---------------------------------------------------------------------------

GROUP_PERMISSIONS = {
    # ------------------------------------------------------------------
    # Instructor Admins
    # Instructors manage the full training syllabus:
    #   - instructors app : training phases, lessons, syllabus documents
    #   - knowledgetest   : question bank (question / category),
    #                       written-test templates + presets,
    #                       view-only access to student attempt records
    # ------------------------------------------------------------------
    "Instructor Admins": [
        # instructors.SyllabusDocument
        ("instructors", "syllabusdocument", "add_syllabusdocument"),
        ("instructors", "syllabusdocument", "change_syllabusdocument"),
        ("instructors", "syllabusdocument", "delete_syllabusdocument"),
        ("instructors", "syllabusdocument", "view_syllabusdocument"),
        # instructors.TrainingLesson
        ("instructors", "traininglesson", "add_traininglesson"),
        ("instructors", "traininglesson", "change_traininglesson"),
        ("instructors", "traininglesson", "delete_traininglesson"),
        ("instructors", "traininglesson", "view_traininglesson"),
        # instructors.TrainingPhase
        ("instructors", "trainingphase", "add_trainingphase"),
        ("instructors", "trainingphase", "change_trainingphase"),
        ("instructors", "trainingphase", "delete_trainingphase"),
        ("instructors", "trainingphase", "view_trainingphase"),
        # knowledgetest.Question
        ("knowledgetest", "question", "add_question"),
        ("knowledgetest", "question", "change_question"),
        ("knowledgetest", "question", "delete_question"),
        ("knowledgetest", "question", "view_question"),
        # knowledgetest.QuestionCategory
        ("knowledgetest", "questioncategory", "add_questioncategory"),
        ("knowledgetest", "questioncategory", "change_questioncategory"),
        ("knowledgetest", "questioncategory", "delete_questioncategory"),
        ("knowledgetest", "questioncategory", "view_questioncategory"),
        # knowledgetest.TestPreset  (added in knowledgetest migration 0005)
        ("knowledgetest", "testpreset", "add_testpreset"),
        ("knowledgetest", "testpreset", "change_testpreset"),
        ("knowledgetest", "testpreset", "delete_testpreset"),
        ("knowledgetest", "testpreset", "view_testpreset"),
        # knowledgetest.WrittenTestAnswer  – view only (student records)
        ("knowledgetest", "writtentestanswer", "view_writtentestanswer"),
        # knowledgetest.WrittenTestAttempt – view only (student records)
        ("knowledgetest", "writtentestattempt", "view_writtentestattempt"),
        # knowledgetest.WrittenTestTemplate  (added in knowledgetest migration 0005)
        ("knowledgetest", "writtentesttemplate", "add_writtentesttemplate"),
        ("knowledgetest", "writtentesttemplate", "change_writtentesttemplate"),
        ("knowledgetest", "writtentesttemplate", "delete_writtentesttemplate"),
        ("knowledgetest", "writtentesttemplate", "view_writtentesttemplate"),
        # knowledgetest.WrittenTestTemplateQuestion
        (
            "knowledgetest",
            "writtentesttemplatequestion",
            "add_writtentesttemplatequestion",
        ),
        (
            "knowledgetest",
            "writtentesttemplatequestion",
            "change_writtentesttemplatequestion",
        ),
        (
            "knowledgetest",
            "writtentesttemplatequestion",
            "delete_writtentesttemplatequestion",
        ),
        (
            "knowledgetest",
            "writtentesttemplatequestion",
            "view_writtentesttemplatequestion",
        ),
    ],
    # ------------------------------------------------------------------
    # Webmasters
    # Webmasters manage site content and configuration:
    #   - cms       : pages, documents, homepage content/images,
    #                 page-role permissions, site feedback, visitor contacts
    #   - siteconfig: site-wide settings, chargeable items, mailing lists,
    #                 membership status definitions
    # ------------------------------------------------------------------
    "Webmasters": [
        # cms.Document
        ("cms", "document", "add_document"),
        ("cms", "document", "change_document"),
        ("cms", "document", "delete_document"),
        ("cms", "document", "view_document"),
        # cms.HomepageContent
        ("cms", "homepagecontent", "add_homepagecontent"),
        ("cms", "homepagecontent", "change_homepagecontent"),
        ("cms", "homepagecontent", "delete_homepagecontent"),
        ("cms", "homepagecontent", "view_homepagecontent"),
        # cms.HomepageImage
        ("cms", "homepageimage", "add_homepageimage"),
        ("cms", "homepageimage", "change_homepageimage"),
        ("cms", "homepageimage", "delete_homepageimage"),
        ("cms", "homepageimage", "view_homepageimage"),
        # cms.Page
        ("cms", "page", "add_page"),
        ("cms", "page", "change_page"),
        ("cms", "page", "delete_page"),
        ("cms", "page", "view_page"),
        # cms.PageMemberPermission (per-member page access overrides)
        ("cms", "pagememberpermission", "add_pagememberpermission"),
        ("cms", "pagememberpermission", "change_pagememberpermission"),
        ("cms", "pagememberpermission", "delete_pagememberpermission"),
        ("cms", "pagememberpermission", "view_pagememberpermission"),
        # cms.PageRolePermission
        ("cms", "pagerolepermission", "add_pagerolepermission"),
        ("cms", "pagerolepermission", "change_pagerolepermission"),
        ("cms", "pagerolepermission", "delete_pagerolepermission"),
        ("cms", "pagerolepermission", "view_pagerolepermission"),
        # cms.SiteFeedback
        ("cms", "sitefeedback", "add_sitefeedback"),
        ("cms", "sitefeedback", "change_sitefeedback"),
        ("cms", "sitefeedback", "delete_sitefeedback"),
        ("cms", "sitefeedback", "view_sitefeedback"),
        # cms.VisitorContact
        ("cms", "visitorcontact", "add_visitorcontact"),
        ("cms", "visitorcontact", "change_visitorcontact"),
        ("cms", "visitorcontact", "delete_visitorcontact"),
        ("cms", "visitorcontact", "view_visitorcontact"),
        # siteconfig.ChargeableItem
        ("siteconfig", "chargeableitem", "add_chargeableitem"),
        ("siteconfig", "chargeableitem", "change_chargeableitem"),
        ("siteconfig", "chargeableitem", "delete_chargeableitem"),
        ("siteconfig", "chargeableitem", "view_chargeableitem"),
        # siteconfig.MailingList
        ("siteconfig", "mailinglist", "add_mailinglist"),
        ("siteconfig", "mailinglist", "change_mailinglist"),
        ("siteconfig", "mailinglist", "delete_mailinglist"),
        ("siteconfig", "mailinglist", "view_mailinglist"),
        # siteconfig.MembershipStatus
        ("siteconfig", "membershipstatus", "add_membershipstatus"),
        ("siteconfig", "membershipstatus", "change_membershipstatus"),
        ("siteconfig", "membershipstatus", "delete_membershipstatus"),
        ("siteconfig", "membershipstatus", "view_membershipstatus"),
        # siteconfig.SiteConfiguration
        ("siteconfig", "siteconfiguration", "add_siteconfiguration"),
        ("siteconfig", "siteconfiguration", "change_siteconfiguration"),
        ("siteconfig", "siteconfiguration", "delete_siteconfiguration"),
        ("siteconfig", "siteconfiguration", "view_siteconfiguration"),
        # logsheet.AircraftMeister
        ("logsheet", "aircraftmeister", "add_aircraftmeister"),
        ("logsheet", "aircraftmeister", "change_aircraftmeister"),
        ("logsheet", "aircraftmeister", "delete_aircraftmeister"),
        ("logsheet", "aircraftmeister", "view_aircraftmeister"),
        # logsheet.Airfield
        ("logsheet", "airfield", "add_airfield"),
        ("logsheet", "airfield", "change_airfield"),
        ("logsheet", "airfield", "delete_airfield"),
        ("logsheet", "airfield", "view_airfield"),
        # logsheet.Flight
        ("logsheet", "flight", "add_flight"),
        ("logsheet", "flight", "change_flight"),
        ("logsheet", "flight", "delete_flight"),
        ("logsheet", "flight", "view_flight"),
        # logsheet.Glider
        ("logsheet", "glider", "add_glider"),
        ("logsheet", "glider", "change_glider"),
        ("logsheet", "glider", "delete_glider"),
        ("logsheet", "glider", "view_glider"),
        # logsheet.Logsheet
        ("logsheet", "logsheet", "add_logsheet"),
        ("logsheet", "logsheet", "change_logsheet"),
        ("logsheet", "logsheet", "delete_logsheet"),
        ("logsheet", "logsheet", "view_logsheet"),
        # logsheet.LogsheetCloseout
        ("logsheet", "logsheetcloseout", "add_logsheetcloseout"),
        ("logsheet", "logsheetcloseout", "change_logsheetcloseout"),
        ("logsheet", "logsheetcloseout", "delete_logsheetcloseout"),
        ("logsheet", "logsheetcloseout", "view_logsheetcloseout"),
        # logsheet.LogsheetPayment
        ("logsheet", "logsheetpayment", "add_logsheetpayment"),
        ("logsheet", "logsheetpayment", "change_logsheetpayment"),
        ("logsheet", "logsheetpayment", "delete_logsheetpayment"),
        ("logsheet", "logsheetpayment", "view_logsheetpayment"),
        # logsheet.MaintenanceDeadline
        ("logsheet", "maintenancedeadline", "add_maintenancedeadline"),
        ("logsheet", "maintenancedeadline", "change_maintenancedeadline"),
        ("logsheet", "maintenancedeadline", "delete_maintenancedeadline"),
        ("logsheet", "maintenancedeadline", "view_maintenancedeadline"),
        # logsheet.MaintenanceIssue
        ("logsheet", "maintenanceissue", "add_maintenanceissue"),
        ("logsheet", "maintenanceissue", "change_maintenanceissue"),
        ("logsheet", "maintenanceissue", "delete_maintenanceissue"),
        ("logsheet", "maintenanceissue", "view_maintenanceissue"),
        # logsheet.MemberCharge
        ("logsheet", "membercharge", "add_membercharge"),
        ("logsheet", "membercharge", "change_membercharge"),
        ("logsheet", "membercharge", "delete_membercharge"),
        ("logsheet", "membercharge", "view_membercharge"),
        # logsheet.RevisionLog
        ("logsheet", "revisionlog", "add_revisionlog"),
        ("logsheet", "revisionlog", "change_revisionlog"),
        ("logsheet", "revisionlog", "delete_revisionlog"),
        ("logsheet", "revisionlog", "view_revisionlog"),
        # logsheet.Towplane
        ("logsheet", "towplane", "add_towplane"),
        ("logsheet", "towplane", "change_towplane"),
        ("logsheet", "towplane", "delete_towplane"),
        ("logsheet", "towplane", "view_towplane"),
        # logsheet.TowplaneChargeScheme
        ("logsheet", "towplanechargescheme", "add_towplanechargescheme"),
        ("logsheet", "towplanechargescheme", "change_towplanechargescheme"),
        ("logsheet", "towplanechargescheme", "delete_towplanechargescheme"),
        ("logsheet", "towplanechargescheme", "view_towplanechargescheme"),
        # logsheet.TowplaneChargeTier
        ("logsheet", "towplanechargetier", "add_towplanechargetier"),
        ("logsheet", "towplanechargetier", "change_towplanechargetier"),
        ("logsheet", "towplanechargetier", "delete_towplanechargetier"),
        ("logsheet", "towplanechargetier", "view_towplanechargetier"),
        # logsheet.TowplaneCloseout
        ("logsheet", "towplanecloseout", "add_towplanecloseout"),
        ("logsheet", "towplanecloseout", "change_towplanecloseout"),
        ("logsheet", "towplanecloseout", "delete_towplanecloseout"),
        ("logsheet", "towplanecloseout", "view_towplanecloseout"),
        # members.Badge
        ("members", "badge", "add_badge"),
        ("members", "badge", "change_badge"),
        ("members", "badge", "delete_badge"),
        ("members", "badge", "view_badge"),
        # members.Biography
        ("members", "biography", "add_biography"),
        ("members", "biography", "change_biography"),
        ("members", "biography", "delete_biography"),
        ("members", "biography", "view_biography"),
    ],
    # ------------------------------------------------------------------
    # Member Managers
    # Member managers handle the membership lifecycle:
    #   - members : full CRUD on Member, Biography, MemberBadge;
    #               view-only on Badge (catalogue is read-only for managers,
    #               only superusers create badges)
    #   - cms     : visiting-pilot contacts and site-feedback triage
    # ------------------------------------------------------------------
    "Member Managers": [
        # cms.SiteFeedback
        ("cms", "sitefeedback", "add_sitefeedback"),
        ("cms", "sitefeedback", "change_sitefeedback"),
        ("cms", "sitefeedback", "delete_sitefeedback"),
        ("cms", "sitefeedback", "view_sitefeedback"),
        # cms.VisitorContact
        ("cms", "visitorcontact", "add_visitorcontact"),
        ("cms", "visitorcontact", "change_visitorcontact"),
        ("cms", "visitorcontact", "delete_visitorcontact"),
        ("cms", "visitorcontact", "view_visitorcontact"),
        # members.Badge  – view only (badge catalogue is admin-managed)
        ("members", "badge", "view_badge"),
        # members.Biography
        ("members", "biography", "add_biography"),
        ("members", "biography", "change_biography"),
        ("members", "biography", "delete_biography"),
        ("members", "biography", "view_biography"),
        # members.Member
        ("members", "member", "add_member"),
        ("members", "member", "change_member"),
        ("members", "member", "delete_member"),
        ("members", "member", "view_member"),
        # members.MemberBadge
        ("members", "memberbadge", "add_memberbadge"),
        ("members", "memberbadge", "change_memberbadge"),
        ("members", "memberbadge", "delete_memberbadge"),
        ("members", "memberbadge", "view_memberbadge"),
    ],
    # ------------------------------------------------------------------
    # Rostermeisters
    # Rostermeisters generate and manage the duty roster:
    #   - duty_roster : full access to assignments, preferences, pairings,
    #                   avoidances, blackouts, swap requests/offers,
    #                   instruction slots, glider reservations, ops intents
    # Note: DutyDay and DutySlot were removed in duty_roster migration 0003;
    # they are intentionally absent from this list.
    # ------------------------------------------------------------------
    "Rostermeisters": [
        # duty_roster.DutyAssignment
        ("duty_roster", "dutyassignment", "add_dutyassignment"),
        ("duty_roster", "dutyassignment", "change_dutyassignment"),
        ("duty_roster", "dutyassignment", "delete_dutyassignment"),
        ("duty_roster", "dutyassignment", "view_dutyassignment"),
        # duty_roster.DutyAvoidance
        ("duty_roster", "dutyavoidance", "add_dutyavoidance"),
        ("duty_roster", "dutyavoidance", "change_dutyavoidance"),
        ("duty_roster", "dutyavoidance", "delete_dutyavoidance"),
        ("duty_roster", "dutyavoidance", "view_dutyavoidance"),
        # duty_roster.DutyPairing
        ("duty_roster", "dutypairing", "add_dutypairing"),
        ("duty_roster", "dutypairing", "change_dutypairing"),
        ("duty_roster", "dutypairing", "delete_dutypairing"),
        ("duty_roster", "dutypairing", "view_dutypairing"),
        # duty_roster.DutyPreference
        ("duty_roster", "dutypreference", "add_dutypreference"),
        ("duty_roster", "dutypreference", "change_dutypreference"),
        ("duty_roster", "dutypreference", "delete_dutypreference"),
        ("duty_roster", "dutypreference", "view_dutypreference"),
        # duty_roster.DutySwapOffer
        ("duty_roster", "dutyswapoffer", "add_dutyswapoffer"),
        ("duty_roster", "dutyswapoffer", "change_dutyswapoffer"),
        ("duty_roster", "dutyswapoffer", "delete_dutyswapoffer"),
        ("duty_roster", "dutyswapoffer", "view_dutyswapoffer"),
        # duty_roster.DutySwapRequest
        ("duty_roster", "dutyswaprequest", "add_dutyswaprequest"),
        ("duty_roster", "dutyswaprequest", "change_dutyswaprequest"),
        ("duty_roster", "dutyswaprequest", "delete_dutyswaprequest"),
        ("duty_roster", "dutyswaprequest", "view_dutyswaprequest"),
        # duty_roster.GliderReservation  (added in duty_roster migration 0005)
        ("duty_roster", "gliderreservation", "add_gliderreservation"),
        ("duty_roster", "gliderreservation", "change_gliderreservation"),
        ("duty_roster", "gliderreservation", "delete_gliderreservation"),
        ("duty_roster", "gliderreservation", "view_gliderreservation"),
        # duty_roster.InstructionSlot
        ("duty_roster", "instructionslot", "add_instructionslot"),
        ("duty_roster", "instructionslot", "change_instructionslot"),
        ("duty_roster", "instructionslot", "delete_instructionslot"),
        ("duty_roster", "instructionslot", "view_instructionslot"),
        # duty_roster.MemberBlackout
        ("duty_roster", "memberblackout", "add_memberblackout"),
        ("duty_roster", "memberblackout", "change_memberblackout"),
        ("duty_roster", "memberblackout", "delete_memberblackout"),
        ("duty_roster", "memberblackout", "view_memberblackout"),
        # duty_roster.OpsIntent
        ("duty_roster", "opsintent", "add_opsintent"),
        ("duty_roster", "opsintent", "change_opsintent"),
        ("duty_roster", "opsintent", "delete_opsintent"),
        ("duty_roster", "opsintent", "view_opsintent"),
        # members.Member  – view only (rostermeisters need to look up members
        #                   when generating and managing the duty roster)
        ("members", "member", "view_member"),
    ],
    # ------------------------------------------------------------------
    # Secretary
    # The Secretary group is created so that Member._sync_groups can assign
    # members with the secretary=True flag to it.  Admin/view access for
    # secretaries is controlled through attribute-level checks on the Member
    # model (getattr(request.user, 'secretary', False)) rather than through
    # model-level Django permissions, so no permissions are granted here.
    # ------------------------------------------------------------------
    "Secretary": [],
    # ------------------------------------------------------------------
    # Treasurer
    # Same pattern as Secretary – the group exists for assignment purposes;
    # permissions are enforced via Member.treasurer field checks in views/admin.
    # ------------------------------------------------------------------
    "Treasurer": [],
}


def _resolve_permissions(Permission, ContentType, perm_tuples):
    """Return a list of Permission objects for the given (app, model, codename) tuples.

    Silently skips any permission/content-type that doesn't exist yet, so this
    function is safe to call during a partial migration run.
    """
    resolved = []
    for app_label, model_name, codename in perm_tuples:
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model_name)
            perm = Permission.objects.get(content_type=ct, codename=codename)
            resolved.append(perm)
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            pass
    return resolved


def setup_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for group_name, perm_tuples in GROUP_PERMISSIONS.items():
        group, created = Group.objects.get_or_create(name=group_name)
        if perm_tuples:
            perms = _resolve_permissions(Permission, ContentType, perm_tuples)
            if perms:
                group.permissions.add(*perms)


def teardown_groups(apps, schema_editor):
    """Reverse migration: remove the permissions we added (don't delete groups).

    Groups are not deleted because they may have members assigned to them, and
    they are re-created by Member._sync_groups on next save anyway.  We only
    remove the permissions this migration granted, leaving any extras untouched.
    """
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for group_name, perm_tuples in GROUP_PERMISSIONS.items():
        try:
            group = Group.objects.get(name=group_name)
        except Group.DoesNotExist:
            continue
        if perm_tuples:
            perms = _resolve_permissions(Permission, ContentType, perm_tuples)
            if perms:
                group.permissions.remove(*perms)


class Migration(migrations.Migration):

    dependencies = [
        # members app: latest migration (defines Badge, Member, Biography, MemberBadge)
        ("members", "0020_add_parent_badge_to_badge"),
        # duty_roster app: latest migration (defines all duty roster models incl. GliderReservation)
        ("duty_roster", "0008_add_singleton_constraint"),
        # cms app: latest migration (defines Page, Document, HomepageContent, etc.)
        ("cms", "0017_alter_pagememberpermission_member"),
        # siteconfig app: latest migration (defines SiteConfiguration, ChargeableItem, MailingList, MembershipStatus)
        ("siteconfig", "0033_enable_instruction_window_for_existing_rows"),
        # logsheet app: latest migration (defines all flight/glider/logsheet models)
        (
            "logsheet",
            "0018_maintenancedeadline_maintenance_deadline_must_have_aircraft",
        ),
        # instructors app: latest migration (defines TrainingPhase, TrainingLesson, SyllabusDocument)
        ("instructors", "0004_add_sort_key_to_traininglesson"),
        # knowledgetest app: latest migration (defines Question, QuestionCategory, TestPreset, WrittenTest*)
        ("knowledgetest", "0005_grant_instructor_admin_knowledgetest_permissions"),
    ]

    operations = [
        migrations.RunPython(setup_groups, teardown_groups),
    ]
