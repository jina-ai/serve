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
MODULE=jina
SRC_NAME="${MODULE}.proto"

COMP_PROTO_OUT_NAME="${MODULE}_pb2.py"
COMP_GRPC_OUT_NAME="${MODULE}_pb2_grpc.py"
PB_NAME="${2:-pb}"
OUT_FOLDER="${PB_NAME}/"

VER_FILE=../__init__.py

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

printf "\e[1;33mfixing grpc import\e[0m\n"
printf "using linux sed syntax, if you are running this on mac, you may want to comment out the sed for linux"
# fix import bug in google generator
# for mac
# sed -i '' -e 's/import\ jina_pb2\ as\ jina__pb2/from\ \.\ import\ jina_pb2\ as\ jina__pb2/' ${SRC_DIR}jina_pb2_grpc.py
# for linux
sed -i "s/import\ docarray_pb2/import\ docarray.proto.${PB_NAME}.docarray_pb2/" "${SRC_DIR}${OUT_FOLDER}jina_pb2.py"
sed -i 's/import\ jina_pb2\ as\ jina__pb2/from\ \.\.\.\ import\ serializer\ as\ jina__pb2/' "${SRC_DIR}${OUT_FOLDER}jina_pb2_grpc.py"

OLDVER=$(sed -n 's/^__proto_version__ = '\''\(.*\)'\''$/\1/p' $VER_FILE)
printf "current proto version:\t\e[1;33m$OLDVER\e[0m\n"

NEWVER=$(echo $OLDVER | awk -F. -v OFS=. 'NF==1{print ++$NF}; NF>1{$NF=sprintf("%0*d", length($NF), ($NF+1)); print}')
printf "bump proto version to:\t\e[1;32m$NEWVER\e[0m\n"

# for mac
# sed -i '' -e 's/^__proto_version__ = '\''\(.*\)'\''/__proto_version__ = '\'"$NEWVER"\''/' $VER_FILE
# for linux
sed -i 's/^__proto_version__ = '\''\(.*\)'\''/__proto_version__ = '\'"$NEWVER"\''/' $VER_FILE



printf "\e[1;32mAll done!\e[0m\n"
printf "if you are running this inside Docker container, you may manually bump proto version to:\t\e[1;32m$NEWVER\e[0m\n"
