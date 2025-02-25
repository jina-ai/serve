import os

import requests
from jina.orchestrate.pods import Pod
from jina.parsers import set_pod_parser

azure_port = 8080


def test_provider_azure_embedding_inference():
    args, _ = set_pod_parser().parse_known_args(
        [
            "--uses",
            os.path.join(
                os.path.dirname(__file__), "SampleColbertExecutor", "config.yml"
            ),
            "--provider",
            "azure",
            "serve",
        ]
    )
    with Pod(args):
        resp = requests.get(f"http://localhost:{azure_port}/ping")
        assert resp.status_code == 200
        assert resp.json() == {}

        resp = requests.post(
            f"http://localhost:{azure_port}/encode",
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


def test_provider_azure_rerank_inference():
    args, _ = set_pod_parser().parse_known_args(
        [
            "--uses",
            os.path.join(
                os.path.dirname(__file__), "SampleColbertExecutor", "config.yml"
            ),
            "--provider",
            "azure",
            "serve",
        ]
    )
    with Pod(args):
        resp = requests.post(
            f"http://localhost:{azure_port}/rank",
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
