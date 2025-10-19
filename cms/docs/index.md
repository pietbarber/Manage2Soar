# CMS docs

This folder contains documentation for the `cms` Django app.

- See `README.md` for a model and route summary.
- ERD: `cms.png` (generated from `cms.dot`)

Regenerate the ERD after model changes with:

```bash
python manage.py graph_models cms -o cms/docs/cms.dot
dot -Tpng cms/docs/cms.dot -o cms/docs/cms.png
```
