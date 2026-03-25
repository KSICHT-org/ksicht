# What is this?

This is the KSICHT [chemistry competition website](https://ksicht.natur.cuni.cz/)
that allows elementary and high schools students to show off theirs skills on
a series of challenging tasks.

The competition takes place annually and consist of 4 quaterly series that
loosely follow the general school year, e.g. starts on autumn and finishes at
late spring. Each series has approx. 5 tasks to complete and contenders
will receive points for each task separately. They can also receive bonus
badges for various acheievements. The contestant to receive the most
points in total, wins.

## Tech details

This app is built with Python powered by [Django](https://www.djangoproject.com/)
with the usual bells and whitles. Styling is based on
the [Bulma CSS framework](https://bulma.io/). We use PostgreSQL as the database.

## Development

Please make sure you have [NVM](https://github.com/nvm-sh/nvm) installed first.

### Installing

Activate NVM:

```bash
nvm use
```

There is a `Makefile` to simplify tasks. Start by creating your Python virtual
env:

```bash
make init-env && source .env/bin/activate
```

Next, install dependencies including the dev and test stuff:

```bash

make install && make install-dev && make install-test
```

You will also need to boostrap your database. By default, a PostgreSQL database named
`ksicht` is expected to exist on your local machine. This can be modified by
overriding the `DATABASE_DSN` env variable when running the app.

First though, you'll need the database to exist:

```bash
createdb ksicht
```

Once there, initialize the database by issuing:

```bash
make migrate
```

This will run Django migrations & will create all the necessary tables.

### Running the app

Just run this:

```bash
make run
```

### Running tests

Again, use the `Makefile`:

```bash
make test
```

### Building & deploying

This app is distributed as a Docker container
and [hosted on Docker Hub](https://hub.docker.com/r/ksicht/web).

#### CI/CD Pipeline

A GitHub Actions workflow (`.github/workflows/main.yml`) automatically builds and pushes the Docker image on every push to `master` or when a version tag is created.

**What happens automatically:**

| Trigger | Docker Hub tags |
|---|---|
| Push to `master` | `latest`, `sha-<short>` |
| Push tag `vX.Y.Z` | `latest`, `X.Y.Z`, `X.Y`, `X` |

#### Creating a release

After merging a PR to `master`, the image is automatically built and pushed as `latest`. To also create a named version:

```bash
git checkout master
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

#### Local builds

Makefile provides commands for local builds:

```bash
make build                    # builds as ksicht/web:latest
make build VERSION=X.Y.Z      # builds as ksicht/web:X.Y.Z
make release                  # builds + pushes (latest by default)
make release VERSION=X.Y.Z    # builds + pushes as ksicht/web:X.Y.Z
```