from game.common.targon import extract_workload_uid, normalize_endpoint_url


def test_normalize_endpoint_url_supports_old_and_new_targon_shapes():
    assert (
        normalize_endpoint_url("serv-u-123")
        == "https://serv-u-123.serverless.targon.com"
    )
    assert normalize_endpoint_url("wrk-abc") == "https://wrk-abc.caas.targon.com"
    assert (
        normalize_endpoint_url("wrk-abc.caas.targon.com")
        == "https://wrk-abc.caas.targon.com"
    )
    assert (
        normalize_endpoint_url("https://wrk-abc.caas.targon.com")
        == "https://wrk-abc.caas.targon.com"
    )


def test_extract_workload_uid_supports_old_and_new_targon_shapes():
    assert extract_workload_uid("serv-u-123") == "serv-u-123"
    assert extract_workload_uid("wrk-abc") == "wrk-abc"
    assert extract_workload_uid("wrk-abc.caas.targon.com") == "wrk-abc"
    assert extract_workload_uid("https://wrk-abc.caas.targon.com") == "wrk-abc"
    assert (
        extract_workload_uid("https://serv-u-123.serverless.targon.com") == "serv-u-123"
    )
