# makespace_storage

This is a storage management system for a maker space, originally
written for makespace.org in Cambridge, UK.

It keeps a database of physical objects, some of which (such as boxes
and shelves) can be used to store other objects.

## Running with Docker

The system runs as three containers: MongoDB, the API server and the
web server.

```sh
cp .env.example .env    # then set the passwords (letters and digits only)
docker compose up -d --build
dev-scripts/loader      # optional: load the sample data via 127.0.0.1:8000
```

The web pages are then at `http://<host>:5000`.  The API is published
only on the host's loopback interface.  The database lives in the
`mongo-data` volume; the application database user is created the
first time MongoDB starts with an empty volume.

On a Raspberry Pi 4 or earlier, set `MONGO_IMAGE=mongo:4.4.18` in
`.env`, because later MongoDB releases need an ARMv8.2-A CPU.  A Pi 5
can use the default `mongo:7`.  Either way a 64-bit OS is required.
