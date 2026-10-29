from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from reversion.admin import VersionAdmin
from tinymce.models import HTMLField
from tinymce.widgets import TinyMCE

from utils.admin_helpers import AdminHelperMixin

from .models import (
    QUALIFICATION_ADMIN_PERMISSION_CODENAMES,
    QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES,
    ClubQualificationType,
    GroundInstruction,
    GroundLessonScore,
    InstructionReport,
    LessonScore,
    MemberQualification,
    QualificationPermissionGrant,
    SyllabusDocument,
    TrainingLesson,
    TrainingPhase,
)


def safe_qualification_permissions():
    """Match the denylist enforced by QualificationPermissionGrant.clean()."""
    return Permission.objects.exclude(
        Q(content_type__app_label__in=("admin", "auth", "contenttypes", "sessions"))
        | Q(
            content_type__app_label="members",
            content_type__model__in=("member", "rolemetadata", "memberroleassignment"),
        )
        | Q(
            content_type__app_label="instructors",
            codename__in=QUALIFICATION_ADMIN_PERMISSION_CODENAMES,
        )
        | Q(codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[0])
        | Q(codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[1])
        | Q(codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[2])
        | Q(codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[3])
    )


def eligible_qualification_groups():
    return Group.objects.filter(
        role_metadata__qualification_permission_bundle=True,
        role_metadata__is_builtin=False,
        role_metadata__is_protected=False,
        role_metadata__is_system_managed=False,
    ).order_by("name")


class QualificationPermissionGrantAdminForm(forms.ModelForm):
    class Meta:
        model = QualificationPermissionGrant
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = eligible_qualification_groups()
        permissions = safe_qualification_permissions()
        self.fields["permission"].queryset = permissions.select_related(
            "content_type"
        ).order_by("content_type__app_label", "codename")


@admin.register(QualificationPermissionGrant)
class QualificationPermissionGrantAdmin(admin.ModelAdmin):
    form = QualificationPermissionGrantAdminForm
    list_display = ("group", "permission")
    list_filter = ("group", "permission__content_type__app_label")
    search_fields = ("group__name", "permission__codename", "permission__name")

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


####################################################
# TrainingLessonAdmin
#
# Admin interface for TrainingLesson model using reversion.
# - list_display: 'code', 'title', 'far_requirement', 'pts_reference'
# - list_filter: 'far_requirement', 'pts_reference'
# - search_fields: 'code', 'title', 'description'
# - ordering: 'code'
####################################################


@admin.register(TrainingLesson)
class TrainingLessonAdmin(AdminHelperMixin, VersionAdmin):
    list_display = ("code", "title", "far_requirement", "pts_reference")
    list_filter = ("far_requirement", "pts_reference")
    search_fields = ("code", "title", "description")
    ordering = ("code",)

    admin_helper_message = "Training lessons: syllabus content for instruction. Edit lesson HTML carefully; used in student progress reports."


####################################################
# TrainingPhaseAdmin
#
# Admin interface for TrainingPhase model using reversion.
# - list_display: 'number', 'name'
# - ordering: 'number'
####################################################


@admin.register(TrainingPhase)
class TrainingPhaseAdmin(AdminHelperMixin, VersionAdmin):
    list_display = ("number", "name")
    ordering = ("number",)

    admin_helper_message = "Training phases: group lessons into phases; changing order affects syllabus structure."


####################################################
# SyllabusDocumentAdmin
#
# Admin interface for SyllabusDocument model using reversion.
# - list_display: 'slug', 'title'
# - search_fields: 'slug', 'title', 'content'
# - formfield_overrides: TinyMCE widget for HTMLField
####################################################


@admin.register(SyllabusDocument)
class SyllabusDocumentAdmin(AdminHelperMixin, VersionAdmin):
    list_display = ("slug", "title")
    search_fields = ("slug", "title", "content")
    formfield_overrides = {
        # apply only to HTMLField fields
        HTMLField: {
            "widget": TinyMCE(
                mce_attrs={
                    "relative_urls": False,  # prevent ugly ../../../ paths
                    "remove_script_host": True,
                    # disable URL conversion to preserve user input (fixes issue #207)
                    "convert_urls": False,
                }
            )
        },
    }

    admin_helper_message = "Syllabus docs: HTML documents used in training pages. Use TinyMCE for content edits."


####################################################
# LessonScoreInline
#
# Inline for editing LessonScore objects within InstructionReport admin.
# - model: LessonScore
# - extra: 0
####################################################


class LessonScoreInline(admin.TabularInline):
    model = LessonScore
    extra = 0


####################################################
# InstructionReportAdmin
#
# Admin interface for InstructionReport model.
# - list_display: 'student', 'instructor', 'report_date'
# - list_filter: 'report_date', 'instructor'
# - search_fields: 'student__last_name', 'instructor__last_name'
# - inlines: [LessonScoreInline]
####################################################


@admin.register(InstructionReport)
class InstructionReportAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("student", "instructor", "report_date")
    list_filter = ("report_date", "instructor")
    search_fields = ("student__last_name", "instructor__last_name")
    inlines = [LessonScoreInline]

    admin_helper_message = "Instruction reports: instructor evaluations for students. Reports are audited and used for qualifications."


####################################################
# LessonScoreAdmin
#
# Admin interface for LessonScore model.
# - list_display: 'report', 'lesson', 'score'
# - list_filter: 'lesson', 'score'
####################################################


@admin.register(LessonScore)
class LessonScoreAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("report", "lesson", "score")
    list_filter = ("lesson", "score")

    admin_helper_message = "Lesson scores: link training lessons to reports. Use inlines on reports for editing."


####################################################
# GroundLessonScoreInline
#
# Inline for editing GroundLessonScore objects within GroundInstruction admin.
# - model: GroundLessonScore
# - extra: 0
####################################################


class GroundLessonScoreInline(admin.TabularInline):
    model = GroundLessonScore
    extra = 0


####################################################
# GroundInstructionAdmin
#
# Admin interface for GroundInstruction model.
# - list_display: 'student', 'instructor', 'date', 'location', 'duration'
# - list_filter: 'date', 'instructor'
# - search_fields: student and instructor names
# - inlines: [GroundLessonScoreInline]
####################################################


@admin.register(GroundInstruction)
class GroundInstructionAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("student", "instructor", "date", "location", "duration")
    list_filter = ("date", "instructor")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "instructor__first_name",
        "instructor__last_name",
    )
    inlines = [GroundLessonScoreInline]

    admin_helper_message = "Ground instruction: non-flight sessions such as briefings or simulator time. Records are used in progress calculations."


####################################################
# ClubQualificationTypeAdmin
#
# Admin interface for ClubQualificationType model.
# - list_display: 'code', 'name', 'applies_to', 'is_obsolete'
# - search_fields: 'code', 'name'
# - list_filter: 'applies_to', 'is_obsolete'
# - ordering: 'code'
####################################################


@admin.register(ClubQualificationType)
class ClubQualificationTypeAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "applies_to",
        "is_obsolete",
        "permission_group",
    )
    search_fields = ("code", "name")
    list_filter = ("applies_to", "is_obsolete")
    ordering = ("code",)

    def _can_manage_permission_group(self, request):
        """Keep qualification permission bundles in the bootstrap admin boundary."""
        return bool(
            request.user and request.user.is_active and request.user.is_superuser
        )

    def get_list_display(self, request):
        fields = super().get_list_display(request)
        if not self._can_manage_permission_group(request):
            return tuple(field for field in fields if field != "permission_group")
        return fields

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Excluding the field from the form, rather than merely hiding its
        # widget, also makes a forged permission_group POST a no-op.  Django's
        # ModelForm then preserves the existing value when saving other fields.
        exclude = list(kwargs.pop("exclude", ()) or ())
        if not self._can_manage_permission_group(request):
            exclude.append("permission_group")
        kwargs["exclude"] = exclude
        return super().get_form(request, obj, change=change, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "permission_group":
            kwargs["queryset"] = (
                Group.objects.filter(
                    qualificationpermissiongrant__isnull=False,
                    role_metadata__qualification_permission_bundle=True,
                    role_metadata__is_builtin=False,
                    role_metadata__is_protected=False,
                    role_metadata__is_system_managed=False,
                )
                .exclude(
                    Q(
                        permissions__content_type__app_label__in=(
                            "admin",
                            "auth",
                            "contenttypes",
                            "sessions",
                        )
                    )
                    | Q(
                        permissions__content_type__app_label="members",
                        permissions__content_type__model__in=(
                            "member",
                            "rolemetadata",
                            "memberroleassignment",
                        ),
                    )
                    | Q(
                        permissions__content_type__app_label="instructors",
                        permissions__codename__in=QUALIFICATION_ADMIN_PERMISSION_CODENAMES,
                    )
                    | Q(
                        permissions__codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                            0
                        ]
                    )
                    | Q(
                        permissions__codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                            1
                        ]
                    )
                    | Q(
                        permissions__codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                            2
                        ]
                    )
                    | Q(
                        permissions__codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                            3
                        ]
                    )
                )
                .distinct()
                .order_by("name")
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    admin_helper_message = "Qualification types: define club qualifications and tooltips. Updates affect member qualifications listings."


####################################################
# MemberQualificationAdmin
#
# Admin interface for MemberQualification model.
# - list_display: 'member', 'qualification', 'is_qualified', 'date_awarded', 'expiration_date', 'imported'
# - search_fields: 'member__username', 'qualification__code'
# - list_filter: 'is_qualified', 'imported', 'qualification__code'
# - autocomplete_fields: 'member', 'qualification', 'instructor'
####################################################


@admin.register(MemberQualification)
class MemberQualificationAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "member",
        "qualification",
        "is_qualified",
        "date_awarded",
        "expiration_date",
        "imported",
    )
    search_fields = ("member__username", "qualification__code")
    list_filter = ("is_qualified", "imported", "qualification__code")
    autocomplete_fields = ("member", "qualification", "instructor")

    admin_helper_message = "Member qualifications: assign or revoke qualifications for members. Prefer issuing via the training workflow."
