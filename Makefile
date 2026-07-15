.PHONY: up dev rw down build logs health clean ps

# Production (default) — read-only ~/.claude mount
up:
	docker compose up --build -d

# Dev frontend with HMR
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Read-write ~/.claude mount
rw:
	docker compose -f docker-compose.yml -f docker-compose.rw.yml up --build -d

# Pull pre-built images from GHCR (no local build)
pull:
	docker compose pull
	docker compose up -d

# Stop all containers
down:
	docker compose down

# Build without starting
build:
	docker compose build

# Follow logs
logs:
	docker compose logs -f

# Follow logs for a specific service (usage: make log-api, make log-frontend, make log-caddy)
log-%:
	docker compose logs -f $*

# Health check
health:
	@curl -sf http://localhost:8080/api/health | python3 -m json.tool || echo "API not healthy"

# Show running containers
ps:
	docker compose ps

# Remove containers, volumes, and orphans
clean:
	docker compose down -v --remove-orphans

# Open dashboard in browser
open:
	open http://localhost:8080
