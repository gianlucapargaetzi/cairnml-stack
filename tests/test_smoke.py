def test_all_packages_import():
    import mlops
    import mlops_agent
    import mlops_common
    import mlops_server

    assert mlops.__version__ == "0.1.1"
    assert mlops_common.__version__ == "0.1.0"
    assert mlops_server.__version__ == "0.2.0"
    assert mlops_agent.__version__ == "0.1.0"
