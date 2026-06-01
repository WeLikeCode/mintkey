module github.com/WeLikeCode/mintkey/apps/ssh-proxy

go 1.22

require (
	github.com/WeLikeCode/mintkey/internal/auditq v0.0.0
	github.com/WeLikeCode/mintkey/internal/changes v0.0.0
	github.com/WeLikeCode/mintkey/internal/otelinit v0.0.0
	github.com/WeLikeCode/mintkey/internal/svcid v0.0.0
	github.com/WeLikeCode/mintkey/internal/ulid v0.0.0
	github.com/WeLikeCode/mintkey/internal/vault v0.0.0
	github.com/go-chi/chi/v5 v5.0.12
	github.com/jackc/pgx/v5 v5.5.5
	github.com/prometheus/client_golang v1.19.0
	go.opentelemetry.io/otel v1.24.0
	go.opentelemetry.io/otel/trace v1.24.0
	golang.org/x/crypto v0.21.0
	google.golang.org/grpc v1.62.1
	modernc.org/sqlite v1.29.5
)

replace (
	github.com/WeLikeCode/mintkey/internal/auditq => ../../internal/auditq
	github.com/WeLikeCode/mintkey/internal/changes => ../../internal/changes
	github.com/WeLikeCode/mintkey/internal/otelinit => ../../internal/otelinit
	github.com/WeLikeCode/mintkey/internal/svcid => ../../internal/svcid
	github.com/WeLikeCode/mintkey/internal/ulid => ../../internal/ulid
	github.com/WeLikeCode/mintkey/internal/vault => ../../internal/vault
)
