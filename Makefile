IMAGE ?= ghcr.io/iitns/k3s-gateway:latest

.PHONY: build push import deploy delete

build:
	docker build -t $(IMAGE) .

push:
	docker push $(IMAGE)

# Import directly into k3s without a registry
import:
	docker save $(IMAGE) | sudo k3s ctr images import -

deploy:
	kubectl apply -f k8s/manifest.yaml

delete:
	kubectl delete -f k8s/manifest.yaml
