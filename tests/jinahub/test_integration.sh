set -ex

docker build --build-arg PIP_TAG="[devel]" --build-arg DOCARRAY_VERSION="0.21.0" -f Dockerfiles/test-pip.Dockerfile -t jinaai/jina:test-pip .
docker build -f tests/jinahub/hub_mwu/Dockerfile tests/jinahub/hub_mwu -t hubpod:test
docker build -f tests/jinahub/Dockerfile tests/jinahub/ -t jinaai/test_hubapp_hubpods

if [ "${PWD##*/}" != "serve" ]
  then
    echo "test_integration.sh should only be run from the serve base directory"
    exit 1
fi

CONTAINER_ID=$(docker run -v /var/run/docker.sock:/var/run/docker.sock -p 45678:45678 --add-host host.docker.internal:host-gateway -d jinaai/test_hubapp_hubpods)

sleep 10

RESPONSE=$(curl --request POST -d '{"data": [{"text": "hey, dude"}]}' -H 'Content-Type: application/json' 'localhost:45678/index')

echo "Response is: ${RESPONSE}"

TEXT_RESPONSE=$(echo $RESPONSE | jq -e ".data[] | .text")

echo "Text Response is: ${TEXT_RESPONSE}"

## remove the new pods
docker ps -a | awk '{ print $1,$2 }' | grep hubpod:test | awk '{print $1 }' | xargs -I {} docker rm -f {}
docker rm -f $CONTAINER_ID

EXPECTED_TEXT='"hey, dude"'

if [ "$EXPECTED_TEXT" = "$TEXT_RESPONSE" ]; then
        echo "Success"
else
        echo "Fail"
        exit 1
fi
