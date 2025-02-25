import csv
import io
import os

import requests
from jina.orchestrate.pods import Pod
from jina.parsers import set_pod_parser

sagemaker_port = 8080


def test_provider_sagemaker_pod_rank():
    args, _ = set_pod_parser().parse_known_args(
        [
            "--uses",
            os.path.join(
                os.path.dirname(__file__), "SampleColbertExecutor", "config.yml"
            ),
            "--provider",
            "sagemaker",
            "--provider-endpoint",
            "rank",
            "serve",  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test the `GET /ping` endpoint (added by jina for sagemaker)
        resp = requests.get(f"http://localhost:{sagemaker_port}/ping")
        assert resp.status_code == 200
        assert resp.json() == {}

        # Test the `POST /invocations` endpoint for inference
        # Note: this endpoint is not implemented in the sample executor
        resp = requests.post(
            f"http://localhost:{sagemaker_port}/invocations",
            json={
                "data": {
                    "documents": [
                        {"text": "the dog is in the house"},
                        {"text": "hey Peter"},
                    ],
                    "query": "where is the dog",
                    "top_n": 2,
                }
            },
        )
        assert resp.status_code == 200
        resp_json = resp.json()
        assert len(resp_json["data"]) == 1
        assert resp_json["data"][0]["results"][0]["document"]["text"] == "first result"


def test_provider_sagemaker_pod_encode():
    args, _ = set_pod_parser().parse_known_args(
        [
            "--uses",
            os.path.join(
                os.path.dirname(__file__), "SampleColbertExecutor", "config.yml"
            ),
            "--provider",
            "sagemaker",
            "--provider-endpoint",
            "encode",
            "serve",  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test the `GET /ping` endpoint (added by jina for sagemaker)
        resp = requests.get(f"http://localhost:{sagemaker_port}/ping")
        assert resp.status_code == 200
        assert resp.json() == {}

        # Test the `POST /invocations` endpoint for inference
        # Note: this endpoint is not implemented in the sample executor
        resp = requests.post(
            f"http://localhost:{sagemaker_port}/invocations",
            json={
                "data": [
                    {"text": "hello world"},
                ]
            },
        )
        assert resp.status_code == 200
        resp_json = resp.json()
        assert len(resp_json["data"]) == 1
        assert len(resp_json["data"][0]["embeddings"][0]) == 64
