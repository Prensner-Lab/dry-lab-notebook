# dry-lab-notebook
Place to find records and results of dry lab activities.

## Deployment

For deployment using `gunicorn` and `nginx`, additional considerations include:

### Static files

`gunicorn` doesn't serve static files.
Instead, delegate the task to `nginx` in two steps:
1. Deposit the project's static files using `python manage.py collectstatic`. 
The location must be accessible by `nginx`, e.g. under `/var/www/dry-lab-notebook/staticfiles/`.
The `Makefile` has a target for this `collectstatic`.
If you update any static files, remember to re-collect.
2. Point `nginx` to these files by putting `location /static/ { alias /var/www/dry-lab-notebook/staticfiles/; }` in the appropriate `server` block (remember, order matters!).
