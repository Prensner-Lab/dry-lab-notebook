#!/bin/sh

set -eu

python manage.py collectstatic --noinput
python manage.py migrate --noinput

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/web.conf