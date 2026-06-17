# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

"""pydantic model of the databag read by the requires side."""

import base64
import binascii
import configparser
import contextlib
import io
from typing import Any, Dict, Optional

from pydantic import BaseModel, Json, SecretStr, validator


class Data(BaseModel):
    """Databag for information shared over the relation."""

    # Required config
    auth_url: Json[str]
    region: Json[str]

    # Userpass auth fields (required for userpass mode, absent for app-cred mode)
    password: Json[Optional[SecretStr]] = None
    project_domain_name: Json[Optional[str]] = None
    project_name: Json[Optional[str]] = None
    username: Json[Optional[str]] = None
    user_domain_name: Json[Optional[str]] = None

    # Application credential fields
    application_credential_id: Json[Optional[str]] = None
    application_credential_name: Json[Optional[str]] = None
    application_credential_secret: Json[Optional[SecretStr]] = None
    auth_type: Json[Optional[str]] = None

    # Optional config
    bs_version: Json[Optional[str]]
    domain_id: Json[Optional[str]] = None
    domain_name: Json[Optional[str]] = None
    endpoint_tls_ca: Json[Optional[str]]
    floating_network_id: Json[Optional[str]]
    has_octavia: Json[Optional[bool]]
    ignore_volume_az: Json[Optional[bool]]
    internal_lb: Json[Optional[bool]]
    lb_enabled: Json[Optional[bool]]
    lb_method: Json[Optional[str]]
    project_id: Json[Optional[str]] = None
    project_domain_id: Json[Optional[str]] = None
    proxy_config: Json[Optional[Dict[str, str]]] = None
    manage_security_groups: Json[Optional[bool]]
    member_subnet_id: Json[Optional[str]] = None
    create_monitor: Json[Optional[bool]] = None
    monitor_delay: Json[Optional[str]] = None
    monitor_timeout: Json[Optional[str]] = None
    monitor_max_retries: Json[Optional[int]] = None
    node_selector: Json[Optional[str]] = None
    internal_network_name: Json[Optional[str]] = None
    public_network_name: Json[Optional[str]] = None
    lb_flavor_id: Json[Optional[str]] = None
    key_id: Json[Optional[str]] = None
    verify_ssl: Json[Optional[bool]] = None
    tls_insecure: Json[Optional[bool]] = None
    verify: Json[Optional[bool]] = None
    additional_cloud_conf_options: Json[Optional[Dict[str, Dict[str, Any]]]] = None
    subnet_id: Json[Optional[str]]
    trust_device_path: Json[Optional[bool]]
    user_domain_id: Json[Optional[str]] = None
    version: Json[Optional[int]] = None

    @staticmethod
    def _quote_ini_string(value: str) -> str:
        """Render INI string values with explicit double quotes."""
        return '"{}"'.format(value.replace('"', r"\""))

    @classmethod
    def _render_ini_value(cls, value: Any) -> str:
        """Render python values to cloud.conf-compatible INI strings."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return cls._quote_ini_string(value)
        return str(value)

    @validator("endpoint_tls_ca")
    def must_be_b64_cert(cls, s: Json[str]):
        """Validate endpoint_tls_ca is base64 encoded str."""
        try:
            base64.b64decode(s, validate=True)
        except binascii.Error:
            raise ValueError("Couldn't find base64 data")
        return s

    @property
    def cloud_config(self) -> str:  # noqa: C901
        """Render as an openstack cloud config ini.

        https://github.com/kubernetes/cloud-provider-openstack/blob/75b1fbb91a2566a869b8922ad62e1c03ab5e6eac/docs/openstack-cloud-controller-manager/using-openstack-cloud-controller-manager.md#global

        """
        _global, _loadbalancer, _blockstorage = {}, {}, {}
        if self.auth_url:
            _global["auth-url"] = self._quote_ini_string(self.auth_url)
        if self.auth_type:
            _global["auth-type"] = self._quote_ini_string(self.auth_type)
        if self.endpoint_tls_ca:
            _global["ca-file"] = self._quote_ini_string("/etc/config/endpoint-ca.cert")
        if self.username:
            _global["username"] = self._quote_ini_string(self.username)
        if self.password:
            _global["password"] = self._quote_ini_string(self.password.get_secret_value())
        if self.region:
            _global["region"] = self._quote_ini_string(self.region)
        if self.application_credential_id:
            _global["application-credential-id"] = self._quote_ini_string(
                self.application_credential_id
            )
        if self.application_credential_name:
            _global["application-credential-name"] = self._quote_ini_string(
                self.application_credential_name
            )
        if self.application_credential_secret:
            _global["application-credential-secret"] = self._quote_ini_string(
                self.application_credential_secret.get_secret_value()
            )
        if self.domain_id:
            _global["domain-id"] = self._quote_ini_string(self.domain_id)
        if self.domain_name:
            _global["domain-name"] = self._quote_ini_string(self.domain_name)
        if self.project_id:
            _global["tenant-id"] = self._quote_ini_string(self.project_id)
        if self.project_name:
            _global["tenant-name"] = self._quote_ini_string(self.project_name)
        if self.project_domain_id:
            _global["tenant-domain-id"] = self._quote_ini_string(self.project_domain_id)
        if self.project_domain_name:
            _global["tenant-domain-name"] = self._quote_ini_string(self.project_domain_name)
        if self.user_domain_id:
            _global["user-domain-id"] = self._quote_ini_string(self.user_domain_id)
        if self.user_domain_name:
            _global["user-domain-name"] = self._quote_ini_string(self.user_domain_name)
        if self.verify_ssl is not None:
            _global["verify-ssl"] = "true" if self.verify_ssl else "false"
        if self.tls_insecure is not None:
            _global["tls-insecure"] = "true" if self.tls_insecure else "false"
        if self.verify is not None:
            _global["verify"] = "true" if self.verify else "false"

        if not self.lb_enabled:
            _loadbalancer["enabled"] = "false"
        if self.has_octavia in (True, None):
            # Newer integrator charm will detect whether underlying OpenStack has
            # Octavia enabled so we can set this intelligently. If we're still
            # related to an older integrator, though, default to assuming Octavia
            # is available.
            _loadbalancer["use-octavia"] = "true"
        else:
            _loadbalancer["use-octavia"] = "false"
            _loadbalancer["lb-provider"] = self._quote_ini_string("haproxy")
        if _s := self.subnet_id:
            _loadbalancer["subnet-id"] = self._quote_ini_string(_s)
        if _s := self.floating_network_id:
            _loadbalancer["floating-network-id"] = self._quote_ini_string(_s)
        if _s := self.lb_method:
            _loadbalancer["lb-method"] = self._quote_ini_string(_s)
        if self.internal_lb:
            _loadbalancer["internal-lb"] = "true"
        if self.manage_security_groups is not None:
            _loadbalancer["manage-security-groups"] = (
                "true" if self.manage_security_groups else "false"
            )
        if _s := self.member_subnet_id:
            _loadbalancer["member-subnet-id"] = self._quote_ini_string(_s)
        if self.create_monitor is not None:
            _loadbalancer["create-monitor"] = "true" if self.create_monitor else "false"
        if _s := self.monitor_delay:
            _loadbalancer["monitor-delay"] = self._quote_ini_string(_s)
        if _s := self.monitor_timeout:
            _loadbalancer["monitor-timeout"] = self._quote_ini_string(_s)
        if self.monitor_max_retries is not None:
            _loadbalancer["monitor-max-retries"] = str(self.monitor_max_retries)
        if _s := self.node_selector:
            _loadbalancer["node-selector"] = self._quote_ini_string(_s)
        if _s := self.lb_flavor_id:
            _loadbalancer["flavor-id"] = self._quote_ini_string(_s)

        if _os := self.bs_version:
            _blockstorage["bs-version"] = self._quote_ini_string(_os)
        if self.trust_device_path is not None:
            _blockstorage["trust-device-path"] = "true" if self.trust_device_path else "false"
        if self.ignore_volume_az is not None:
            _blockstorage["ignore-volume-az"] = "true" if self.ignore_volume_az else "false"

        config = configparser.ConfigParser()
        config["Global"] = _global
        config["LoadBalancer"] = _loadbalancer
        config["BlockStorage"] = _blockstorage
        if self.internal_network_name or self.public_network_name:
            config["Networking"] = {}
            if self.internal_network_name:
                config["Networking"]["internal-network-name"] = self._quote_ini_string(
                    self.internal_network_name
                )
            if self.public_network_name:
                config["Networking"]["public-network-name"] = self._quote_ini_string(
                    self.public_network_name
                )
        if self.key_id:
            config["KeyManager"] = {"key-id": self._quote_ini_string(self.key_id)}

        if self.additional_cloud_conf_options:
            for section, values in self.additional_cloud_conf_options.items():
                if section not in config:
                    config[section] = {}
                for key, value in values.items():
                    config[section][key] = self._render_ini_value(value)

        with contextlib.closing(io.StringIO()) as sio:
            config.write(sio)
            output_text = sio.getvalue()

        return output_text
