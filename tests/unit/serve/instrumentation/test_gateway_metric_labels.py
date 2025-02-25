from jina import DocumentArray, Executor, Flow, requests


def test_gateway_metric_labels(monkeypatch_metric_exporter):
    collect_metrics, read_metrics = monkeypatch_metric_exporter

    class FirstExec(Executor):
        @requests()
        def meow(self, docs, **kwargs):
            return DocumentArray.empty(3)

    class SecondExec(Executor):
        @requests()
        def meow(self, docs, **kwargs):
            return DocumentArray.empty(3)

    with Flow(
        tracing=False,
        metrics=True,
        metrics_exporter_host='http://localhost',
        metrics_exporter_port=4317,
        port=12345,
    ).add(name='first_exec', uses=FirstExec).add(
        name="second_exec", uses=SecondExec
    ) as f:
        f.post('/')
        collect_metrics()
        metrics = read_metrics()
        gateway_metrics = metrics['gateway/rep-0']['resource_metrics'][0][
            'scope_metrics'
        ][0]['metrics']
        gateway_metric_data_point = {
            i['name']: i['data']['data_points'] for i in gateway_metrics
        }

    assert (
        'address'
        in gateway_metric_data_point['jina_sending_request_seconds'][0]['attributes']
    )
    assert (
        'address'
        in gateway_metric_data_point['jina_sent_request_bytes'][0]['attributes']
    )
    assert (
        'address'
        in gateway_metric_data_point['jina_received_response_bytes'][0]['attributes']
    )
    assert (
        'address'
        in gateway_metric_data_point['jina_sending_request_seconds'][1]['attributes']
    )
    assert (
        'address'
        in gateway_metric_data_point['jina_sent_request_bytes'][1]['attributes']
    )
    assert (
        'address'
        in gateway_metric_data_point['jina_received_response_bytes'][1]['attributes']
    )

    assert (
        'deployment'
        in gateway_metric_data_point['jina_sending_request_seconds'][0]['attributes']
    )
    assert (
        'deployment'
        in gateway_metric_data_point['jina_sent_request_bytes'][0]['attributes']
    )
    assert (
        'deployment'
        in gateway_metric_data_point['jina_received_response_bytes'][0]['attributes']
    )
    assert (
        'deployment'
        in gateway_metric_data_point['jina_sending_request_seconds'][1]['attributes']
    )
    assert (
        'deployment'
        in gateway_metric_data_point['jina_sent_request_bytes'][1]['attributes']
    )
    assert (
        'deployment'
        in gateway_metric_data_point['jina_received_response_bytes'][1]['attributes']
    )

    assert {'first_exec', 'second_exec'} == {
        i['attributes']['deployment']
        for i in gateway_metric_data_point['jina_received_response_bytes']
    }
    assert {'first_exec', 'second_exec'} == {
        i['attributes']['deployment']
        for i in gateway_metric_data_point['jina_sent_request_bytes']
    }
    assert {'first_exec', 'second_exec'} == {
        i['attributes']['deployment']
        for i in gateway_metric_data_point['jina_sending_request_seconds']
    }


def test_merge_with_no_reduce(monkeypatch_metric_exporter):
    collect_metrics, read_metrics = monkeypatch_metric_exporter

    f = (
        Flow(
            tracing=False,
            metrics=True,
            metrics_exporter_host='http://localhost',
            metrics_exporter_port=4317,
            port=12345,
        )
        .add(name='name1')
        .add(name='name2', needs=['gateway'])
        .add(name='name3', needs=['name1', 'name2'], disable_reduce=True)
    )
    with f:
        f.post('/')
        collect_metrics()
        metrics = read_metrics()

        gateway_metrics = metrics['gateway/rep-0']['resource_metrics'][0][
            'scope_metrics'
        ][0]['metrics']
        gateway_metric_data_point = {
            i['name']: i['data']['data_points'] for i in gateway_metrics
        }

    assert {'name1', 'name2', 'name3'} == {
        i['attributes']['deployment']
        for i in gateway_metric_data_point['jina_received_response_bytes']
    }
    assert {'name1', 'name2', 'name3'} == {
        i['attributes']['deployment']
        for i in gateway_metric_data_point['jina_sent_request_bytes']
    }
    assert {'name1', 'name2', 'name3'} == {
        i['attributes']['deployment']
        for i in gateway_metric_data_point['jina_sending_request_seconds']
    }
