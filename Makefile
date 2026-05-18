# ChainGuard-Core — developer convenience Makefile
# Phase 1+: wraps the most common Minikube / Helm / kubectl flows so you can
# bring the whole local stack up with `make infra-up` and verify with
# `make validate`.

SHELL          := /usr/bin/env bash
.SHELLFLAGS    := -eu -o pipefail -c
.DEFAULT_GOAL  := help

NAMESPACE      ?= default
KAFKA_RELEASE  ?= chain-kafka
DB_RELEASE     ?= chain-db

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
.PHONY: help
help:  ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} \
		/^[a-zA-Z0-9_.-]+:.*##/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Phase 1 — Local infrastructure
# ---------------------------------------------------------------------------
.PHONY: infra-up
infra-up:  ## Start Minikube + Kafka + Postgres + Vector DB
	./scripts/bootstrap-infra.sh

.PHONY: infra-down
infra-down:  ## Uninstall Helm releases + vector-db (cluster stays up)
	./scripts/teardown-infra.sh

.PHONY: infra-stop
infra-stop:  ## Soft teardown then minikube stop
	./scripts/teardown-infra.sh --full

.PHONY: infra-nuke
infra-nuke:  ## DESTRUCTIVE: delete the Minikube cluster entirely
	./scripts/teardown-infra.sh --nuke

.PHONY: pods
pods:  ## Show pods in the chainguard namespace
	kubectl get pods -n $(NAMESPACE)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
.PHONY: validate
validate: validate-pg validate-vector  ## Run all Phase 1 acceptance checks

.PHONY: validate-pg
validate-pg:  ## Run SELECT version() against chain-db
	./scripts/validate-postgres.sh

.PHONY: validate-vector
validate-vector:  ## Create/get/delete a Qdrant collection via localhost:6333
	python3 scripts/validate-vector-db.py

# ---------------------------------------------------------------------------
# Port-forwards (run in separate terminals as needed)
# ---------------------------------------------------------------------------
.PHONY: port-forward-vector
port-forward-vector:  ## Forward vector-db 6333/6334 to localhost
	kubectl port-forward -n $(NAMESPACE) svc/vector-db 6333:6333 6334:6334

.PHONY: port-forward-pg
port-forward-pg:  ## Forward postgres 5432 to localhost
	kubectl port-forward -n $(NAMESPACE) svc/$(DB_RELEASE)-postgresql 5432:5432

.PHONY: port-forward-kafka
port-forward-kafka:  ## Forward Kafka 9092 to localhost
	kubectl port-forward -n $(NAMESPACE) svc/$(KAFKA_RELEASE) 9092:9092

# ---------------------------------------------------------------------------
# C++ engine (Phase 2)
# ---------------------------------------------------------------------------
.PHONY: cpp-build
cpp-build:  ## Configure + build the C++ engine
	cmake -B build -S . -DCMAKE_BUILD_TYPE=Release
	cmake --build build --parallel

.PHONY: cpp-run
cpp-run: cpp-build  ## Run the chainguard binary (no-op build smoke)
	./build/bin/chainguard

.PHONY: cpp-probe
cpp-probe: cpp-build  ## Verify Kafka broker connectivity (needs port-forward-kafka)
	./build/bin/chainguard --probe --brokers $${KAFKA_BROKERS:-localhost:9092}

.PHONY: cpp-smoke
cpp-smoke: cpp-build  ## Produce 10 records and verify zero drops (Phase 2.1 acceptance)
	./build/bin/chainguard --smoke --brokers $${KAFKA_BROKERS:-localhost:9092}

.PHONY: cpp-ingest
cpp-ingest: cpp-build  ## Stream a WebSocket and parse ticks (Ctrl-C to stop)
	./build/bin/chainguard --ingest --ws-url $${WS_URL:-ws://localhost:8765/}

.PHONY: cpp-throughput
cpp-throughput: cpp-build  ## Benchmark parser (Phase 2.2 acceptance: ≥20k tps)
	./build/bin/chainguard --throughput-test $${THROUGHPUT_N:-1000000}

.PHONY: cpp-engine
cpp-engine: cpp-build  ## Full pipeline: WS → ring → features → Kafka topic 'financial-features'
	./build/bin/chainguard --engine \
		--ws-url $${WS_URL:-ws://localhost:8765/} \
		--brokers $${KAFKA_BROKERS:-localhost:9092}

.PHONY: cpp-feature-bench
cpp-feature-bench: cpp-build  ## Frame-gen latency bench (Phase 2.3 acceptance: median <50µs)
	./build/bin/chainguard --feature-bench

# ---------------------------------------------------------------------------
# Phase 3 — Container image
# ---------------------------------------------------------------------------
IMAGE_NAME ?= chainguard-core
IMAGE_TAG  ?= dev

.PHONY: docker-build
docker-build:  ## Build the multi-stage container image
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

.PHONY: docker-size
docker-size: docker-build  ## Print final image size in MB (Phase 3.1 acceptance: <150MB)
	@bytes=$$(docker image inspect $(IMAGE_NAME):$(IMAGE_TAG) --format '{{.Size}}'); \
	mb=$$(( bytes / 1024 / 1024 )); \
	echo "image size: $$mb MB"; \
	if [ $$mb -ge 150 ]; then \
	    echo "  → FAIL: exceeds 150MB ceiling"; exit 1; \
	else \
	    echo "  → meets acceptance (< 150MB)"; \
	fi

.PHONY: docker-run
docker-run:  ## Run --version inside the container
	docker run --rm $(IMAGE_NAME):$(IMAGE_TAG) --version

.PHONY: docker-shell
docker-shell:  ## Probe the distroless layout via debug variant (one-off debugging)
	docker run --rm -it --entrypoint=/busybox/sh \
	    $(IMAGE_NAME):$(IMAGE_TAG)-debug || \
	    echo "Build with: docker build -t $(IMAGE_NAME):$(IMAGE_TAG)-debug --target builder ."

# ---------------------------------------------------------------------------
# Phase 3.2 — Kubernetes deployment + KEDA
# ---------------------------------------------------------------------------
.PHONY: keda-install
keda-install:  ## Install KEDA into the local cluster (namespace: keda)
	./scripts/install-keda.sh

.PHONY: image-load
image-load: docker-build  ## Load $(IMAGE_NAME):$(IMAGE_TAG) into Minikube so the pod can pull it
	minikube image load $(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: k8s-deploy
k8s-deploy:  ## Apply k8s/deployment.yaml + k8s/keda-scaledobject.yaml
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/keda-scaledobject.yaml

.PHONY: k8s-undeploy
k8s-undeploy:  ## Tear down the chainguard Deployment + ScaledObject
	kubectl delete -f k8s/keda-scaledobject.yaml --ignore-not-found
	kubectl delete -f k8s/deployment.yaml --ignore-not-found

.PHONY: flood-kafka
flood-kafka:  ## Phase 3.2 acceptance: 50k records → KEDA scale-out
	./scripts/flood-kafka.sh $${FLOOD_N:-50000}

.PHONY: watch-pods
watch-pods:  ## Watch chainguard pods + the KEDA-managed HPA
	@echo "Ctrl-C to stop."
	kubectl get pods,hpa -l app.kubernetes.io/name=chainguard-engine --watch

# ---------------------------------------------------------------------------
# Phase 4.1 — Python classifier + Airflow
# ---------------------------------------------------------------------------
CLASSIFIER_IMAGE_NAME ?= chainguard-classifier
CLASSIFIER_IMAGE_TAG  ?= dev

.PHONY: init-postgres
init-postgres:  ## Apply scripts/sql/init.sql to chain-db
	./scripts/init-postgres.sh

.PHONY: classifier-test
classifier-test:  ## Run pytest against the classifier package
	cd services/classifier && PYTHONPATH=.. pytest -q tests

.PHONY: classifier-train-baseline
classifier-train-baseline:  ## Generate services/classifier/models/baseline.txt
	PYTHONPATH=services python3 services/classifier/scripts/train_baseline.py

.PHONY: classifier-build
classifier-build:  ## Build the classifier image (also bakes baseline.txt)
	docker build -f services/classifier/Dockerfile \
	    -t $(CLASSIFIER_IMAGE_NAME):$(CLASSIFIER_IMAGE_TAG) .

.PHONY: classifier-load
classifier-load: classifier-build  ## Load into Minikube
	minikube image load $(CLASSIFIER_IMAGE_NAME):$(CLASSIFIER_IMAGE_TAG)

.PHONY: classifier-deploy
classifier-deploy:  ## Apply k8s/classifier-deployment.yaml
	kubectl apply -f k8s/classifier-deployment.yaml

.PHONY: classifier-undeploy
classifier-undeploy:  ## Remove the classifier Deployment + PVC + ConfigMap
	kubectl delete -f k8s/classifier-deployment.yaml --ignore-not-found

.PHONY: airflow-install
airflow-install:  ## helm install Apache Airflow (DAGs mounted from ConfigMap)
	./scripts/install-airflow.sh

.PHONY: airflow-ui
airflow-ui:  ## Port-forward the Airflow webserver to localhost:8080
	kubectl port-forward -n $${AIRFLOW_NAMESPACE:-airflow} svc/airflow-webserver 8080:8080

# ---------------------------------------------------------------------------
# Phase 4.2 — LangGraph 3-tier agent cluster
# ---------------------------------------------------------------------------
AGENTS_IMAGE_NAME ?= chainguard-agents
AGENTS_IMAGE_TAG  ?= dev

.PHONY: agents-test
agents-test:  ## pytest the agents package (state schema + graph routing)
	cd services/agents && PYTHONPATH=.. pytest -q tests

.PHONY: agents-build
agents-build:  ## Build the agents container image
	docker build -f services/agents/Dockerfile \
	    -t $(AGENTS_IMAGE_NAME):$(AGENTS_IMAGE_TAG) .

.PHONY: agents-load
agents-load: agents-build  ## Load the agents image into Minikube
	minikube image load $(AGENTS_IMAGE_NAME):$(AGENTS_IMAGE_TAG)

.PHONY: agents-seed
agents-seed:  ## Seed Qdrant with attack-vector exemplars (port-forward-vector first)
	PYTHONPATH=services python3 services/agents/seed_vector_db.py \
	    --url $${QDRANT_URL:-http://localhost:6333}

.PHONY: agents-deploy
agents-deploy:  ## Apply k8s/agents-deployment.yaml
	kubectl apply -f k8s/agents-deployment.yaml

.PHONY: agents-undeploy
agents-undeploy:  ## Remove the agents Deployment + ConfigMap + Secret
	kubectl delete -f k8s/agents-deployment.yaml --ignore-not-found

.PHONY: agents-set-openai-key
agents-set-openai-key:  ## Inject OPENAI_API_KEY env into the Secret (reads $$OPENAI_API_KEY)
	@test -n "$$OPENAI_API_KEY" || (echo "set OPENAI_API_KEY first" && exit 1)
	kubectl create secret generic chainguard-agents-secrets \
	    --from-literal=OPENAI_API_KEY=$$OPENAI_API_KEY \
	    --dry-run=client -o yaml | kubectl apply -f -

.PHONY: mock-ticker
mock-ticker:  ## Run the dev WebSocket ticker on ws://localhost:8765 (Ctrl-C to stop)
	python3 scripts/mock-ticker.py --rate $${MOCK_RATE:-25000}

.PHONY: cpp-clean
cpp-clean:  ## Remove the local CMake build directory
	rm -rf build
