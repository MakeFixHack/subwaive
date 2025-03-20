# Setup for SubWaive

## .env file

The expected key-value pairs in the `.env` file are:

```
DEBUG=False
DJANGO_SECRET_KEY=
DJANGO_LOGLEVEL=info
DJANGO_ALLOWED_HOSTS=localhost,sig-swipe
TIME_ZONE=

DATABASE_ENGINE=postgresql_psycopg2
DATABASE_NAME=subwaivedb
DATABASE_USERNAME=subwaive
DATABASE_PASSWORD=
DATABASE_HOST=subwaive-db
DATABASE_PORT=5432

STRIPE_API_KEY=
STRIPE_ENDPOINT_SECRET=
STRIPE_WWW_ENDPOINT=https://dashboard.stripe.com/

DOCUSEAL_API_KEY=
DOCUSEAL_API_ENDPOINT=
DOCUSEAL_WWW_ENDPOINT=

CALENDAR_URL=
```

Missing values are either secrets you need to collect/establish or setup-specific values, like a time zone or a resource.


## Initializing Django

Establish the initial data model and superuser:

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata initial
```

## Docker network connections

Create the Docker network with:

```sh
docker network create subwaive
```

SubWaive needs to have both services added to an external network that can be shared with Docuseal:

```
services:
  db:
  ...
    networks:
      -subwaive
  django-web:
  ...
    networks:
      -subwaive
networks:
 subwaive:
    external: true
```

Docuseal also needs to have its networks updated. The `postgres` service needs to be added to the `mfh` network for us to run SQL against that database. The `app` service needs to be added so we can make API requests against it and so it can `POST` webhooks.

```
services:
  app:
  ...
    networks:
      -subwaive
      - default
 networks:
 subwaive:
    external: true
  default:
```

### View Docker network

To see if each container is attached to the network you defined:

```sh
docker network inspect subwaive
```

This will also give the name of the containers you should use as hostnames in your configurations for things like:

* Webhook endpoints
* Database hostname
* DJANGO_ALLOWED_HOSTS

## Expected Docuseal configurations

* Waivers live in a folder called "Waivers"

