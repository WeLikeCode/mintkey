# Registered by `l4 init`: the harness's tests carry @pytest.mark.l4(...).


def pytest_configure(config):
    config.addinivalue_line("markers", "l4(*ids): the acceptance criteria (C-xxxxxxxx) this test checks")
