# Liquibase migration runner for Mintkey. The k8s liquibase Job can't bind-mount
# the changelog (as docker-compose did), so bundle it into the image. The chart
# runs `--changeLogFile=changelog/db.changelog-master.yaml` from /liquibase.
FROM liquibase/liquibase:4.27.0@sha256:141a9fb5df99e43be49e507dc1892a65cd7b93c9e662c4212e834468df959983

# Trivy gate (container-scan.yml): fix what is fixable instead of allow-listing it.
#  - gpgv: apt security update (CVE-2025-68973).
#  - pgjdbc: replace the bundled 42.7.2 with the pinned 42.7.12 (CVE-2026-42198, CVE-2026-54291);
#    Mintkey only migrates Postgres.
#  - mssql-jdbc, snowflake-jdbc, lpm: unused by Mintkey (Postgres only, no
#    liquibase package manager), and carry their own HIGH CVEs; removed.
USER root
ADD --checksum=sha256:31fbf6f06b2217fb51d5100cee51b22625cc81640da0679b47914e54c1e6377c \
    https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.12/postgresql-42.7.12.jar \
    /liquibase/internal/lib/postgresql.jar
RUN apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade gpgv \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /liquibase/internal/lib/mssql-jdbc.jar /liquibase/internal/lib/snowflake-jdbc.jar /liquibase/bin/lpm \
 && chmod 0644 /liquibase/internal/lib/postgresql.jar
USER liquibase
COPY apps/admin-api/db/changelog /liquibase/changelog
