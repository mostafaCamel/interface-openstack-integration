# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import base64
import unittest.mock as mock
from pathlib import Path

import pytest
import yaml
from ops.charm import CharmBase, RelationBrokenEvent

from ops.interface_openstack_integration import OpenstackIntegrationRequirer


@pytest.fixture(scope="function")
def requirer():
    mock_charm = mock.MagicMock(auto_spec=CharmBase)
    mock_charm.framework.model.unit.name = "test/0"
    yield OpenstackIntegrationRequirer(mock_charm)


@pytest.fixture()
def relation_data():
    yield yaml.safe_load(Path("tests/data/openstack_integration_data.yaml").open())


@pytest.mark.parametrize(
    "event_type", [None, RelationBrokenEvent], ids=["unrelated", "dropped relation"]
)
def test_is_ready_no_relation(requirer, event_type):
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.__bool__.return_value = event_type is not None
        relation.units = []
        event = mock.MagicMock(spec=event_type)
        event.relation = relation
        assert requirer.is_ready is False
        assert "Missing" in requirer.evaluate_relation(event)
        assert requirer.cloud_conf is None
        assert requirer.endpoint_tls_ca is None


def test_is_ready_invalid_data(requirer, relation_data):
    relation_data["version"] = 123
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": relation_data}
        assert requirer.is_ready is False


def test_is_ready_success(requirer, relation_data):
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": relation_data}
        assert requirer.is_ready is True


def test_create_config_ini(requirer, relation_data, tmpdir):
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": relation_data}

        expected = Path("tests/data/cloud_conf.ini").read_text()
        assert requirer.cloud_conf == expected
        assert requirer.cloud_conf_b64 == base64.b64encode(expected.encode())


@pytest.fixture()
def appcred_relation_data():
    yield yaml.safe_load(Path("tests/data/openstack_appcred_data.yaml").open())


def test_is_ready_appcred(requirer, appcred_relation_data):
    """is_ready should be True when application credentials are present."""
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": appcred_relation_data}
        assert requirer.is_ready is True


def test_is_ready_appcred_missing_secret(requirer, appcred_relation_data):
    """is_ready should be False when app-cred secret is absent."""
    appcred_relation_data["application_credential_secret"] = "null"
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": appcred_relation_data}
        assert requirer.is_ready is False


def test_create_config_ini_appcred(requirer, appcred_relation_data):
    """cloud_conf should contain application-credential keys and omit username/password."""
    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": appcred_relation_data}
        conf = requirer.cloud_conf
        assert 'application-credential-id = "app-cred-id-123"' in conf
        assert 'application-credential-name = "my-app-cred"' in conf
        assert 'application-credential-secret = "app-cred-secret-456"' in conf
        assert 'auth-type = "v3applicationcredential"' in conf
        assert "username" not in conf
        assert "password" not in conf


def test_create_config_ini_extended_options(requirer, relation_data):
    """cloud_conf should render extended options for all supported sections."""
    relation_data.update(
        {
            "verify_ssl": "false",
            "tls_insecure": "true",
            "verify": "false",
            "member_subnet_id": '"member-subnet-id"',
            "create_monitor": "true",
            "monitor_delay": '"10s"',
            "monitor_timeout": '"5s"',
            "monitor_max_retries": "3",
            "node_selector": '"juju-application=k8s-worker"',
            "lb_flavor_id": '"flavor-id-1"',
            "internal_network_name": '"internal-net"',
            "public_network_name": '"public-net"',
            "key_id": '"barbican-key-id"',
            "trust_device_path": "false",
            "ignore_volume_az": "false",
        }
    )

    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": relation_data}
        conf = requirer.cloud_conf

    assert "verify-ssl = false" in conf
    assert "tls-insecure = true" in conf
    assert "verify = false" in conf
    assert "manage-security-groups = false" in conf
    assert 'member-subnet-id = "member-subnet-id"' in conf
    assert "create-monitor = true" in conf
    assert 'monitor-delay = "10s"' in conf
    assert 'monitor-timeout = "5s"' in conf
    assert "monitor-max-retries = 3" in conf
    assert 'node-selector = "juju-application=k8s-worker"' in conf
    assert 'flavor-id = "flavor-id-1"' in conf
    assert "[Networking]" in conf
    assert 'internal-network-name = "internal-net"' in conf
    assert 'public-network-name = "public-net"' in conf
    assert "[KeyManager]" in conf
    assert 'key-id = "barbican-key-id"' in conf
    assert "trust-device-path = false" in conf
    assert "ignore-volume-az = false" in conf


def test_create_config_ini_additional_cloud_conf_options(requirer, relation_data):
    relation_data.update(
        {
            "additional_cloud_conf_options": (
                '{"LoadBalancer":{"availability-zone":"AG1"},' '"Global":{"max-retries":3}}'
            )
        }
    )

    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": relation_data}
        conf = requirer.cloud_conf

    assert "[LoadBalancer]" in conf
    assert 'availability-zone = "AG1"' in conf
    assert "[Global]" in conf
    assert "max-retries = 3" in conf


def test_create_config_ini_additional_cloud_conf_options_override(requirer, relation_data):
    relation_data.update(
        {
            "manage_security_groups": "false",
            "additional_cloud_conf_options": ('{"LoadBalancer":{"manage-security-groups":true}}'),
        }
    )

    with mock.patch.object(
        OpenstackIntegrationRequirer, "relation", new_callable=mock.PropertyMock
    ) as mock_prop:
        relation = mock_prop.return_value
        relation.units = ["remote/0"]
        relation.data = {"remote/0": relation_data}
        conf = requirer.cloud_conf

    assert "manage-security-groups = true" in conf
