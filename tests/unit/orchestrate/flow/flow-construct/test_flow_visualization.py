import imghdr
import os
import struct

import pytest

from jina import Executor, Flow

cur_dir = os.path.dirname(os.path.abspath(__file__))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_visualization_with_yml_file_img(tmpdir):
    Flow.load_config(
        os.path.join(cur_dir, '../../../yaml/test_flow_visualization.yml')
    ).plot(output=os.path.join(tmpdir, 'flow.svg'))
    assert os.path.exists(os.path.join(tmpdir, 'flow.svg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_visualization_with_yml_file_jpg(tmpdir):
    Flow.load_config(
        os.path.join(cur_dir, '../../../yaml/test_flow_visualization.yml')
    ).plot(output=os.path.join(tmpdir, 'flow.jpg'))
    assert os.path.exists(os.path.join(tmpdir, 'flow.jpg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_visualization_with_yml_file_jpg_lr(tmpdir):
    Flow.load_config(
        os.path.join(cur_dir, '../../../yaml/test_flow_visualization.yml')
    ).plot(output=os.path.join(tmpdir, 'flow-hor.jpg'), vertical_layout=False)
    assert os.path.exists(os.path.join(tmpdir, 'flow-hor.jpg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_visualization_plot_twice(tmpdir):
    (
        Flow()
            .add(name='pod_a')
            .plot(output=os.path.join(tmpdir, 'flow1.svg'))
            .add(name='pod_b', needs='gateway')
            .needs(['pod_a', 'pod_b'])
            .plot(output=os.path.join(tmpdir, 'flow2.svg'))
    )

    assert os.path.exists(os.path.join(tmpdir, 'flow1.svg'))
    assert os.path.exists(os.path.join(tmpdir, 'flow2.svg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_visualization_plot_in_middle(tmpdir):
    (
        Flow()
            .add(name='pod_a')
            .plot(output=os.path.join(tmpdir, 'flow3.svg'))
            .add(name='pod_b', needs='gateway')
            .needs(['pod_a', 'pod_b'])
    )

    assert os.path.exists(os.path.join(tmpdir, 'flow3.svg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_flow_before_after_plot(tmpdir):
    Flow().add(uses_before=Executor, uses_after=Executor, name='p1').plot(
        os.path.join(tmpdir, 'flow.svg')
    )
    assert os.path.exists(os.path.join(tmpdir, 'flow.svg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_flow_before_plot(tmpdir):
    Flow().add(uses_before=Executor, name='p1').plot(os.path.join(tmpdir, 'flow.svg'))
    assert os.path.exists(os.path.join(tmpdir, 'flow.svg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
def test_flow_after_plot(tmpdir):
    Flow().add(uses_after=Executor, name='p1').plot(os.path.join(tmpdir, 'flow.svg'))
    assert os.path.exists(os.path.join(tmpdir, 'flow.svg'))


@pytest.mark.skipif("GITHUB_WORKFLOW" in os.environ, reason="Skip unneeded")
@pytest.mark.parametrize('vertical_layout', [True, False])
def test_flow_vertical(tmpdir, vertical_layout):
    def get_image_size(fname):
        with open(fname, 'rb') as fh:
            head = fh.read(24)
            if len(head) != 24:
                return
            if imghdr.what(fname) == 'png':
                check = struct.unpack('>i', head[4:8])[0]
                if check != 0x0D0A1A0A:
                    return
                width, height = struct.unpack('>ii', head[16:24])
            elif imghdr.what(fname) == 'jpeg':
                try:
                    fh.seek(0)  # Read 0xff next
                    size = 2
                    ftype = 0
                    while not 0xC0 <= ftype <= 0xCF:
                        fh.seek(size, 1)
                        byte = fh.read(1)
                        while ord(byte) == 0xFF:
                            byte = fh.read(1)
                        ftype = ord(byte)
                        size = struct.unpack('>H', fh.read(2))[0] - 2
                    # We are at a SOFn block
                    fh.seek(1, 1)  # Skip `precision' byte.
                    height, width = struct.unpack('>HH', fh.read(4))
                except Exception:  # IGNORE:W0703
                    return
            else:
                return
            return width, height

    output_fn = str(tmpdir / 'flow.png')
    Flow().add(name='a').add(name='b').plot(output_fn, vertical_layout=vertical_layout)
    assert os.path.exists(output_fn)
    w_h = get_image_size(output_fn)
    assert w_h is not None
    w, h = w_h
    assert (w < h) == vertical_layout
