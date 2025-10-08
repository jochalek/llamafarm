#! /bin/bash
set -e

echo "Compiling config schema..."
uv run python compile_schema.py

echo "Generating config types..."
uv run datamodel-codegen \
    --input schema.deref.yaml \
    --output datamodel.py \
    --input-file-type=jsonschema \
    --output-model-type=pydantic_v2.BaseModel \
    --target-python-version=3.12 \
    --use-standard-collections \
    --formatters=ruff-format \
    --class-name=LlamaFarmConfig

echo "Generating agents service types..."
cd ../agents
uv run datamodel-codegen \
    --input schema.yaml \
    --output datamodel.py \
    --input-file-type=jsonschema \
    --output-model-type=pydantic_v2.BaseModel \
    --target-python-version=3.12 \
    --use-standard-collections \
    --formatters=ruff-format

echo "Done! Generated types for config and agents service."
