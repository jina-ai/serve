#!/usr/bin/env bash
set -e

# Do NOT use this directly, use jinaai/protogen image
# use jinaai/protogen:v21 in order to use compiler version == 21 (creates pb/docarray_pb2.py)
# and use jinaai/protogen:latest to use compiler version <= 20 (creates pb2/docarray_pb2.py)
# make sure to use jinaai/protogen:v21 to avoid overwriting the module
#
# current dir: jina root (the one with README.md)
# run the following in bash:
# docker run -v $(pwd)/jina/proto/docarray_v2:/jina/proto jinaai/protogen
# finally, set back owner of the generated files using: sudo chown -R $(id -u ${USER}):$(id -g ${USER}) ./jina/proto

# The protogen docker image can also be build locally using:
# docker build -f Dockerfiles/protogen.Dockerfile -t jinaai/protogen:local .
# or
# docker build -f Dockerfiles/protogen-3.21.Dockerfile -t jinaai/protogen-3.21:local .

SRC_DIR=./
SRC_NAME="add_voter.proto"

PB_NAME="${2:-pb}"
OUT_FOLDER="${PB_NAME}/"

if [ "$#" -ne 1 ] && [ "$#" -ne 2 ]; then
    echo "Error: Please specify the [PATH_TO_GRPC_PYTHON_PLUGIN], refer more details at " \
      "https://jina.ai/serve/"
    printf "\n"
    echo "USAGE:"
    printf "\t"
    echo "bash ./build-proto.sh [PATH_TO_GRPC_PYTHON_PLUGIN]"
    exit 1
fi

PLUGIN_PATH=${1}  # /Volumes/TOSHIBA-4T/Documents/grpc/bins/opt/grpc_python_plugin

printf "\e[1;33mgenerating protobuf and grpc python interface\e[0m\n"

protoc -I ${SRC_DIR} --python_out="${SRC_DIR}${OUT_FOLDER}" --grpc_python_out="${SRC_DIR}${OUT_FOLDER}" --plugin=protoc-gen-grpc_python=${PLUGIN_PATH} ${SRC_DIR}${SRC_NAME}
sed -i 's/import add_voter_pb2 as add__voter__pb2/from . import add_voter_pb2 as add__voter__pb2/' "${PB_NAME}/add_voter_pb2_grpc.py"
printf "\e[1;32mAll done!\e[0m\n"