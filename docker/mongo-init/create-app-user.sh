#!/bin/bash
# Run once by the official mongo image, the first time it starts with
# an empty data volume.  Creates the database user the API server
# logs in as.  The API authenticates against the application database
# itself (authSource=DATABASE_NAME), so the user is created there.
#
# "${mongo[@]}" and _js_escape are provided by the image's
# docker-entrypoint.sh; they work with both the legacy `mongo` shell
# (4.4 images) and `mongosh` (5.0+ images).
set -e

"${mongo[@]}" "$MONGO_INITDB_DATABASE" <<EOJS
db.createUser({
    user: $(_js_escape "$MONGOUSER"),
    pwd: $(_js_escape "$MONGOPASSWORD"),
    roles: [{ role: "readWrite", db: $(_js_escape "$MONGO_INITDB_DATABASE") }]
});
EOJS
