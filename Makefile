
start-minikube:
	bash ./infra/minikube/start-minikube.sh

install-kafka:
	bash ./infra/kafka/install-kafka.sh

test-kafka:
	bash ./infra/kafka/test-kafka.sh
