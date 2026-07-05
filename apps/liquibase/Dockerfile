# Liquibase migration runner for Mintkey. The k8s liquibase Job can't bind-mount
# the changelog (as docker-compose did), so bundle it into the image. The chart
# runs `--changeLogFile=changelog/db.changelog-master.yaml` from /liquibase.
FROM liquibase/liquibase:4.27.0
COPY apps/admin-api/db/changelog /liquibase/changelog
