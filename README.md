# dry-lab-notebook
Place to find records and results of dry lab activities.

## Deployment

### Container

A `Dockerfile` has been prepared for serving the `django` app.
Using `docker compose`, two separate containers can be deployed, one for development and one for production.
The main difference is that the dev server is `manage.py runserver` and the prod server is `gunicorn` and `nginx`.
At the time of writing, `nginx` is not included in the container.
See instructions below on how to configure your system for `nginx` integration.

To make sure the prod container persists, you may need to prevent your host system will not kill your processes when your session ends.
One way to do this is to enable "lingering" for your user with `loginctl enable-linger $USER`.
Then, when you start a container tied to your user, it will not be killed as soon as you log out.

### Static files for `nginx`

`gunicorn` doesn't serve static files.
Instead, delegate the task to `nginx` in two steps:
1. Deposit the project's static files using `python manage.py collectstatic`. 
The location must be accessible by `nginx`, e.g. under `/var/www/dry-lab-notebook/staticfiles/`.
The `Makefile` has a target for this `collectstatic`.
This target depends on env var `STATICFILE_HOST_DIR` to put the static files in the right place.
If you update any static files, remember to re-collect.
2. Point `nginx` to these files by putting `location /static/ { alias /var/www/dry-lab-notebook/staticfiles/; }` in the appropriate `server` block (remember, order matters!).

## Configuring Globus

One of the attractive features of Dry Lab Notebook is that is provides unauthenicated access to certain Globus resources.
This is possible because the app has its own Globus client which you can grant access to specific resources that are relevant to your lab.

However, not all operations on Globus resources can or should be performed by this client.
Transfers, for instance, are best delegated to a user's own Globus identity.
This is preferable (among other reasons) because it allows the user to monitior the transfer via `app.globus.org`.

### Collections and Indexes

The administrator of a Dry Lab Notebook instance defines which collections and search indexes that instance will use.

#### Collection access

The app's client can only access Guest collections (not Mapped collections).
Guest collections (as the name suggests) accommodate users who don't have a login on the underlying system, which is the case for the app's client.
To authorize the app client to access your desired Globus resources, visit the collection on `app.globus.org`, go to "Permissions", and add the app using its UUID.

#### Search data visibility

As opposed to authorizing a client to access a specific collection, access to data in Globus Search involves a visibility control on the per-record level.
Each "entry" (a sub-record of a given "subject") in a Search index is associated with a principal (or list of principals) which defines who gets to access that data.
Therefore, for your client to be able to see any of your Search data, you must assign each record with a principal URN which includes your client.
This could be the principal URN of your client itself, however it is more practical to create a group which has access and use the group's URN.
