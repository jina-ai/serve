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
            os.path.join(os.path.dirname(__file__), "SampleClipExecutor", "config.yml"),
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
                    {"url": "http://google.com"},
                ]
            },
        )
        assert resp.status_code == 200
        resp_json = resp.json()
        assert len(resp_json["data"]) == 1
        assert len(resp_json["data"][0]["embeddings"][0]) == 64
        assert resp_json["data"][0]["url"] == "http://google.com"


def test_provider_sagemaker_pod_batch_transform_valid():
    args, _ = set_pod_parser().parse_known_args(
        [
            "--uses",
            os.path.join(os.path.dirname(__file__), "SampleClipExecutor", "config.yml"),
            "--provider",
            "sagemaker",
            "serve",  # This is added by sagemaker
        ]
    )
    with Pod(args):
        # Test `POST /invocations` endpoint for batch-transform with valid input
        with open(
            os.path.join(os.path.dirname(__file__), "valid_clip_input.csv"), "r"
        ) as f:
            csv_data = f.read()

        text = []
        for line in csv.reader(
            io.StringIO(csv_data),
            delimiter=",",
            quoting=csv.QUOTE_NONE,
            escapechar="\\",
        ):
            text.append(line)

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
        assert len(resp_json["data"]) == 3
        assert resp_json["data"][0]["text"] == "the cat is in my house"
        assert (
            resp_json["data"][1]["url"]
            == "https://dummyimage3.com/333/000/fff.jpg&text=embed+this"
        )
        assert "hWjj1RNtNftP" in resp_json["data"][2]["bytes"]
