# Setup for SubWaive

Establish the initial data model and superuser:

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata initial
```

# Docker network connections

This probably isn't needed at the point where something is publicly accessible.

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

# View Docker network

To see if each container is attached to the network you defined:

```sh
docker network inspect subwaive
```

This will also give the name of the containers you should use as hostnames in your configurations for things like:

* Webhook endpoints
* Database hostname
* DJANGO_ALLOWED_HOSTS

# Expected Docuseal configurations

* Waivers live in a folder called "Waivers"

