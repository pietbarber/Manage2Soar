import pytest
from django.core.files.storage import default_storage
from django.urls import reverse

from cms.models import Page


@pytest.mark.django_db
def test_page_breadcrumbs_and_doc_count(client, django_user_model, monkeypatch):
    # Prevent storage backend from attempting to fetch missing blobs
    monkeypatch.setattr(default_storage, "size", lambda name: 0)
    # Create a simple page hierarchy: parent -> child
    parent = Page.objects.create(title="Parent page", slug="parent", is_public=True)
    child = Page.objects.create(
        title="Child page", slug="child", parent=parent, is_public=True
    )

    # Add one document to parent, two to child
    parent.documents.create(title="Parent doc", file="files/parent.pdf")
    child.documents.create(title="Child doc 1", file="files/child1.pdf")
    child.documents.create(title="Child doc 2", file="files/child2.pdf")

    # Request the parent page (use the cms app url name)
    url = reverse("cms:cms_page", kwargs={"path": parent.slug})
    resp = client.get(url)
    assert resp.status_code == 200

    # Breadcrumbs should include Resources (home) and parent
    breadcrumbs = resp.context.get("breadcrumbs")
    assert breadcrumbs is not None
    assert any(crumb["title"].lower().startswith("resources") for crumb in breadcrumbs)

    # The view should annotate subpages with doc_count = own docs + child docs
    subpages = resp.context.get("subpages")
    assert subpages is not None
    # Find the child entry and assert doc_count is 2
    child_entry = next((s for s in subpages if s["page"].pk == child.pk), None)
    assert child_entry is not None
    assert child_entry["doc_count"] == 2
