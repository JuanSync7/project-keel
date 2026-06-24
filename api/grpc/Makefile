.PHONY: gen
gen: ## Generate Python stubs from the proto
	python -m grpc_tools.protoc -I proto \
		--python_out=. --grpc_python_out=. proto/thing.proto
