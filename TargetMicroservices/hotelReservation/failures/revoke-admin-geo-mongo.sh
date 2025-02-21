# Copyright (c) Microsoft Corporation
# Licensed under the Apache License, Version 2.0. See LICENSE file in the project root for full license information.

#!/bin/bash

ADMIN_USER="admin"
ADMIN_PWD="admin"
# TARGET_DB="rate-db"
TARGET_DB="geo-db"

echo "Downgrading admin user privileges..."

# Connect to MongoDB and revoke roles
mongo admin -u $ADMIN_USER -p $ADMIN_PWD --authenticationDatabase admin \
     --eval "db.revokeRolesFromUser('$ADMIN_USER', [{role: 'readWrite', db: '$TARGET_DB'}]);"

echo "Privileges downgraded"

