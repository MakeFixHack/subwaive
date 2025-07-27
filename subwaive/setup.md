# Setup for SubWaive

## The .env file

SubWaive uses an environment file to define secrets, such as passwords, and configurations, such as timezones.

The expected key-value pairs in the `.env` file are:

```
DEBUG=False
DJANGO_SECRET_KEY=
DJANGO_LOGLEVEL=info
DJANGO_ALLOWED_HOSTS=localhost,subwaive
CSRF_TRUSTED_ORIGINS=http://localhost,http://subwaive
TIME_ZONE=America/New_York

DATA_REFRESH_TOKEN=

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
DOCUSEAL_ENDPOINT_SECRET=
DOCUSEAL_API_ENDPOINT=
DOCUSEAL_WWW_ENDPOINT=

CALENDAR_URL=
CALENDAR_WWW_ENDPOINT=
```

Missing values are either secrets you need to collect/establish or setup-specific values, like a time zone or a resource.

SubWaive will not load until the following keys are populated:

* DJANGO_SECRET_KEY
* DATABASE_PASSWORD

`DJANGO_SECRET_KEY`, `DATABASE_PASSWORD`, and `DOCUSEAL_ENDPOINT_SECRET` can be generated with the following Python:

```python
from django.core.management.utils import get_random_secret_key

print(f"""DJANGO_SECRET_KEY={ get_random_secret_key() }\n
DATABASE_PASSWORD={ get_random_secret_key() }\n
DOCUSEAL_ENDPOINT_SECRET={ get_random_secret_key() }\n
DATA_REFRESH_TOKEN={ get_random_secret_key() }""")
```

You must update the `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` keys for the frontend to not fail security checks. The Docker network for communicating between containers requires the hostname for SubWaive an element in these lists.

## Docker network connections

If you are running Docuseal in a Docker container, such as in a development environment, this section is required. If your instance of Docuseal is not in a docker container (or can ), you can choose not to create the network and remove the references to the `subwaive` network from `compose.yaml`.

When initializing Django, we created the Docker network with:

```sh
# create a Docker network
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

Docuseal also needs to have its networks updated. The `app` service needs to be added so we can make API requests against it and so it can `POST` webhooks.

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

## Initializing Django

Establish the initial data model and superuser:

```sh
# create expected Docker network
docker network create subwaive

# instantiate the container
docker build -t subwaive .

# create and run the container in detached mode
docker compose up --build --detach

# migrate database changes know by Django but not yet by Postgres
docker exec -it subwaive python manage.py migrate

# install initial database fixtures
docker exec -it subwaive python manage.py loaddata initial
```

The initial data loaded creates a super user called `admin` with a password of `makefixhack`. If you don't change that password immediately, you get what you deserve. 😄

## Single Sign On with OIDC

SubWaive has optional support for two forms of authentication:

1. Django's built-in auth system (always enabled)
2. OIDC

### Configuration

To configure OIDC a set of key-value pairs must be added to the `.env` file.

To turn on SSO:

```
IS_USE_OIDC_LOGIN=True
```

Authentication details:

```
OIDC_RP_SIGN_ALGO=
OIDC_RP_CLIENT_ID=
OIDC_RP_CLIENT_SECRET=
```

SubWaive hosting details:

```
LOGIN_REDIRECT_URL=
LOGOUT_REDIRECT_URL=
```

> Use http://localhost/ for a local development instance.

SSO server endpoints:

```
OIDC_OP_TOKEN_ENDPOINT=
OIDC_OP_AUTHORIZATION_ENDPOINT=
OIDC_OP_JWKS_ENDPOINT=
OIDC_OP_USER_ENDPOINT=
```

> Fully formed URLs you can find in your OpenID Configuration for the OIDC client.

Missing values are specific to your OIDC configuration and `client`.

### Providers

By default, SubWaive is designed to work with [Keycloak](https://www.keycloak.org/). 

For other providers you may need to modify `subwaive/subwaive/backends.py` to provide different keys for the dictionary `claims`, which is used to populate meaningful user information.

### User privileges

When SubWaive creates a local user for a new SSO login, it provides that user access to the `Admin Console`. The `Admin Console` allows them to perform certain tasks that are not exposed by SubWaive's web interface. To that end, SubWaive provides the new user with privileges so they can view, add, remove, and change a select number of database models:

* Person - name updates and additions
* PersonEmail - email address management
* QRCategory - managing custom QR code categories
* QRCustom - managing custom QR codes

The `admin` user can modify these permissions once established. To change the set of privileges provided to new users, modify the list `codenames` in `subwaive/subwaive/backends.py`.

### Logging in

When SSO is enabled, a different log-in page is used. The custom log-in page provides a button for signing in with your SSO provider and a button to reveal the built-in login (for the admin and any other local accounts).

### Logging out

Logout is handled by the `Admin Console` regardless of authentication method.

## Docuseal integration

Docuseal can be downloaded and installed from:

* https://github.com/docusealco/docuseal/blob/master/README.md

When building template documents for waivers and other documents, make note of the fields you wish to extract into SubWaive and add them to the DocusealField model. They will be scraped using the Docuseal API when you:

1. Refresh Docuseal data
2. A submission is updated because of a webhook

SubWaive considers any document contained in a folder called `Waivers` to be a waiver. In Docuseal, you should create a `Waivers` folder and place your waiver documents there.

To hide a document from SubWaive, archive it.

### API

Docuseal has an API which requires an API key to be copied into the `.env` file. The API key can be found in the Docuseal settings menu, along with the API secret.

The relevant `.env` keys are:

* DOCUSEAL_API_KEY - your Docuseal API key
* DOCUSEAL_API_ENDPOINT - your Docuseal API address, from API examples in settings

### Webhooks

SubWaive can update Docuseal data in bulk or selectively. An initial bulk refresh is recommended, especially if a significant number of documents have been signed.

> IMPORTANT
> Webhooks should use HTTPS or internal networks to prevent snooping and impersonation, as Docuseal does not use HMAC signatures, and instead sends the secret as a plain-text header.

For routine updates, configure Docuseal webhooks that point to the SubWaive-Docuseal webhook URL:

* https://`hostname`/docuseal/webhook/

This address will trigger a selective update based on the payload provided by Docuseal.

> NOTE
> Subwaive does not trust the information in webhooks. Instead, entity IDs are stripped out and the API is used to get data for performing database updates.

Webhooks for Docuseal are also configured through the settings menu and require the webhook secret to be added to the `.env` file.

In Docuseal, you must turn on webhooks in settings before you can add the secret. The webhooks currently handled by SubWaive are:

* form.completed
* template.created
* template.updated
* submission.created
* submission.archived

The webhook header key is `X-Docuseal-Signature`.

#### Troubleshooting

* Log show `/` as `CSRF violation`: check the webhook address in Docuseal points to `https://hostname/docuseal/webhook/`

### Building links

SubWaive builds links for various objects in its interface. Linking directly to Docuseal allows user access but only on the basis of having Docuseal credentials. This limits the ability of users to see certain information.

The relevant `.env` keys are:

* DOCUSEAL_WWW_ENDPOINT - your Docuseal web address, for building URLs

## Stripe integration

* All sales options are represented by a payment link
* All product prices have a price description

### API

Stripe has an API which requires an API key to be copied into the `.env` file. An API key for SubWaive should be created using the limited key option. The restricted key reduces the chances the access to the API key can result in unauthorized transaction.

API keys are created in the developer's console at the bottom left corner of the dashboard.

Create a limited/restricted API key for SubWaive with the follow `read` access:

* Core > Customers
* Core > Products
* Checkout > Checkout sessions
* Billing > Prices
* Billing > Subscriptions
* Payment links > Payment links

The relevant `.env` keys are:

* STRIPE_API_KEY - the API key built for this app

### Webhooks

TDB - which hooks do you need?

* STRIPE_ENDPOINT_SECRET -

### Building links

SubWaive builds links for various objects in its interface. Linking directly to Stripe allows user access but only on the basis of having Stripe credentials. This limits the ability of user to see certain information.

For production Stripe data:

* STRIPE_WWW_ENDPOINT=https://dashboard.stripe.com/

For test Stripe data:

* STRIPE_WWW_ENDPOINT=https://dashboard.stripe.com/

## Calendar integration

SubWaive reads in calendar events in order to provide a "check-in" feature for monitoring attendance. Check-ins allow you to view a person's history with events and the attendance at events.

This provides a away to:

* Compare, and monitor over time, the popularity of events
* Watch for members who are not visiting as much (low engagement => cancellation risk)

The relevant `.env` keys are:

* CALENDAR_URL - the local used to download the ical file containing the calendar
* CALENDAR_WWW_ENDPOINT- your public calendar's address, for building URLs

## Cronjobs

To maintain a reasonably current dataset, SubWaive uses `cron` to periodically update the external datasources. To verify that requests for updates are authorized, a secret key is stored in:

* DATA_REFRESH_TOKEN -  a user provided token for authenticating requests for data refreshes

Since SubWaive communicates these requests over its Docker network, no additional security is provided.

### Troubleshooting

* Logs report `subwaive:8000` should be added to `ALLOWED_HOSTS`: add `subwaive` to `DJANGO_ALLOWED_HOSTS` in your `.env` file
