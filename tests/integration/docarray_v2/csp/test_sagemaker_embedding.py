import csv
import io
import os
import time

import pytest
import requests

from jina import Deployment
from jina.helper import random_port
from jina.orchestrate.pods import Pod
from jina.parsers import set_pod_parser

cur_dir = os.path.dirname(os.path.abspath(__file__))
sagemaker_port = 8080


@pytest.fixture
def replica_docker_image_built():
    import docker

    client = docker.from_env()
    client.images.build(path=os.path.join(cur_dir), tag='sampler-executor')
    client.close()
    yield
    time.sleep(2)
    client = docker.from_env()
    client.containers.prune()


def test_provider_sagemaker_pod_inference():
    args, _ = set_pod_parser().parse_known_args(
        [
            '--uses',
            os.path.join(os.path.dirname(__file__), "SampleExecutor", "config.yml"),
            '--provider',
            'sagemaker',
            "--provider-endpoint",
            "encode",
            'serve',  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test the `GET /ping` endpoint (added by jina for sagemaker)
        resp = requests.get(f'http://localhost:{sagemaker_port}/ping')
        assert resp.status_code == 200
        assert resp.json() == {}

        # Test the `POST /invocations` endpoint for inference
        # Note: this endpoint is not implemented in the sample executor
        resp = requests.post(
            f'http://localhost:{sagemaker_port}/invocations',
            json={
                'data': [
                    {'text': 'hello world'},
                ]
            },
        )
        assert resp.status_code == 200
        resp_json = resp.json()
        assert len(resp_json['data']) == 1
        assert len(resp_json['data'][0]['embeddings'][0]) == 64


def test_provider_sagemaker_pod_inference_parameters():
    args, _ = set_pod_parser().parse_known_args(
        [
            '--uses',
            os.path.join(os.path.dirname(__file__), "SampleExecutor", "config.yml"),
            '--provider',
            'sagemaker',
            "--provider-endpoint",
            "encode_parameter",
            'serve',  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test the `GET /ping` endpoint (added by jina for sagemaker)
        resp = requests.get(f'http://localhost:{sagemaker_port}/ping')
        assert resp.status_code == 200
        assert resp.json() == {}
        for emb_dim in {32, 64, 128}:

            # Test the `POST /invocations` endpoint for inference
            # Note: this endpoint is not implemented in the sample executor
            resp = requests.post(
                f'http://localhost:{sagemaker_port}/invocations',
                json={
                    'data': [
                        {'text': 'hello world'},
                    ],
                    'parameters': {'emb_dim': emb_dim}
                },
            )
            assert resp.status_code == 200
            resp_json = resp.json()
            assert len(resp_json['data']) == 1
            assert len(resp_json['data'][0]['embeddings'][0]) == emb_dim



@pytest.mark.parametrize(
    "filename",
    [
        "valid_input_1.csv",
        "valid_input_2.csv",
    ],
)
def test_provider_sagemaker_pod_batch_transform_valid(filename):
    args, _ = set_pod_parser().parse_known_args(
        [
            '--uses',
            os.path.join(os.path.dirname(__file__), "SampleExecutor", "config.yml"),
            '--provider',
            'sagemaker',
            "--provider-endpoint",
            "encode",
            'serve',  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test `POST /invocations` endpoint for batch-transform with valid input
        texts = []
        with open(os.path.join(os.path.dirname(__file__), filename), "r") as f:
            csv_data = f.read()

        for line in csv.reader(
            io.StringIO(csv_data),
            delimiter=",",
            quoting=csv.QUOTE_NONE,
            escapechar="\\",
        ):
            texts.append(line[1])

        resp = requests.post(
            f"http://localhost:{sagemaker_port}/invocations",
            headers={
                "accept": "application/json",
                "content-type": "text/csv",
            },
            data=csv_data,
        )
        assert resp.status_code == 200
        resp_json = resp.json()
        assert len(resp_json["data"]) == 10
        for idx, d in enumerate(resp_json["data"]):
            assert d["text"] == texts[idx]
            assert len(d["embeddings"][0]) == 64


def test_provider_sagemaker_pod_batch_transform_invalid():
    args, _ = set_pod_parser().parse_known_args(
        [
            '--uses',
            os.path.join(os.path.dirname(__file__), "SampleExecutor", "config.yml"),
            '--provider',
            'sagemaker',
            "--provider-endpoint",
            "encode",
            'serve',  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test `POST /invocations` endpoint for batch-transform with invalid input
        with open(
            os.path.join(os.path.dirname(__file__), 'invalid_input.csv'), 'r'
        ) as f:
            csv_data = f.read()

        resp = requests.post(
            f'http://localhost:{sagemaker_port}/invocations',
            headers={
                'accept': 'application/json',
                'content-type': 'text/csv',
            },
            data=csv_data,
        )
        assert resp.status_code == 400
        assert (
            resp.json()['detail']
            == "Invalid CSV format. Line ['abcd'] doesn't match the expected field "
            "order ['id', 'text']."
        )


def test_provider_sagemaker_deployment_inference():
    dep_port = random_port()
    with Deployment(
        uses=os.path.join(os.path.dirname(__file__), "SampleExecutor", "config.yml"),
        provider='sagemaker',
        provider_endpoint='encode',
        port=dep_port,
    ):
        # Test the `GET /ping` endpoint (added by jina for sagemaker)
        rsp = requests.get(f'http://localhost:{dep_port}/ping')
        assert rsp.status_code == 200
        assert rsp.json() == {}

        # Test the `POST /invocations` endpoint
        # Note: this endpoint is not implemented in the sample executor
        rsp = requests.post(
            f'http://localhost:{dep_port}/invocations',
            json={
                'data': [
                    {'text': 'hello world'},
                ]
            },
        )
        assert rsp.status_code == 200
        resp_json = rsp.json()
        assert len(resp_json['data']) == 1
        assert len(resp_json['data'][0]['embeddings'][0]) == 64


def test_provider_sagemaker_deployment_inference_docker(replica_docker_image_built):
    dep_port = random_port()
    with Deployment(
        uses='docker://sampler-executor', provider='sagemaker', provider_endpoint='encode', port=dep_port
    ):
        # Test the `GET /ping` endpoint (added by jina for sagemaker)
        rsp = requests.get(f'http://localhost:{dep_port}/ping')
        assert rsp.status_code == 200
        assert rsp.json() == {}

        # Test the `POST /invocations` endpoint
        # Note: this endpoint is not implemented in the sample executor
        rsp = requests.post(
            f'http://localhost:{dep_port}/invocations',
            json={
                'data': [
                    {'text': 'hello world'},
                ]
            },
        )
        assert rsp.status_code == 200
        resp_json = rsp.json()
        assert len(resp_json['data']) == 1
        assert len(resp_json['data'][0]['embeddings'][0]) == 64


@pytest.mark.skip('Sagemaker with Deployment for batch-transform is not supported yet')
def test_provider_sagemaker_deployment_batch():
    dep_port = random_port()
    with Deployment(
        uses=os.path.join(os.path.dirname(__file__), "SampleExecutor", "config.yml"),
        provider='sagemaker',
        provider_endpoint='encode',
        port=dep_port,
    ):
        # Test the `POST /invocations` endpoint for batch-transform
        with open(os.path.join(os.path.dirname(__file__), 'valid_input.csv'), 'r') as f:
            csv_data = f.read()

        rsp = requests.post(
            f'http://localhost:{dep_port}/invocations',
            headers={
                'accept': 'application/json',
                'content-type': 'text/csv',
            },
            data=csv_data,
        )
        assert rsp.status_code == 200
        resp_json = rsp.json()
        assert len(resp_json['data']) == 10
        for d in resp_json['data']:
            assert len(d['embeddings'][0]) == 64


def test_provider_sagemaker_deployment_wrong_port():
    # Sagemaker executor would start on 8080.
    # If we use the same port for deployment, it should raise an error.
    with pytest.raises(ValueError):
        with Deployment(
            uses=os.path.join(
                os.path.dirname(__file__), "SampleExecutor", "config.yml"
            ),
            provider='sagemaker',
            provider_endpoint='encode',
            port=8080,
        ):
            pass


def test_provider_sagemaker_deployment_wrong_dynamic_batching():
    # Sagemaker executor would start on 8080.
    # If we use the same port for deployment, it should raise an error.
    from jina.excepts import RuntimeFailToStart

    with pytest.raises(RuntimeFailToStart) as exc:
        with Deployment(
            uses=os.path.join(
                os.path.dirname(__file__), "SampleExecutor", "config.yml"
            ),
            provider='sagemaker',
            provider_endpoint='encode_parameter',
            uses_dynamic_batching={'/encode_parameter': {'preferred_batch_size': 20, 'timeout': 50}},
        ):
            pass
