import os
import time

import pytest

from jina import Deployment, Executor


class SlowExecutor(Executor):
    def close(self) -> None:
        with open(
            os.path.join(self.metas.workspace, 'test'), 'w', encoding='utf-8'
        ) as f:
            time.sleep(10)
            f.write('x')


@pytest.mark.slow
def test_slow_executor_close(tmpdir):
    with Deployment(protocol='http',
        uses={'jtype': 'SlowExecutor', 'with': {}, 'metas': {'workspace': str(tmpdir)}}, include_gateway=False,
    ):
        pass

    assert os.path.exists(os.path.join(tmpdir, 'test'))
