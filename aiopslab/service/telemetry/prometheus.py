# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import json
import yaml
import time
from subprocess import CalledProcessError
from aiopslab.service.helm import Helm
from aiopslab.service.kubectl import KubeCtl
from aiopslab.paths import PROMETHEUS_METADATA, BASE_DIR


class Prometheus:
    def __init__(self):
        self.config_file = PROMETHEUS_METADATA
        self.name = None
        self.namespace = None
        self.helm_configs = {}
        self.pv_config_file = None

        self.load_service_json()

    def load_service_json(self):
        """Load metric service metadata into attributes."""
        with open(self.config_file, "r") as file:
            metadata = json.load(file)

        self.name = metadata.get("Name")
        self.namespace = metadata.get("Namespace")

        self.helm_configs = metadata.get("Helm Config", {})
        if "chart_path" in self.helm_configs:
            chart_path = self.helm_configs["chart_path"]
            self.helm_configs["chart_path"] = str(BASE_DIR / chart_path)
        
        self.pv_config_file = str(BASE_DIR / metadata.get("PersistentVolumeConfig"))

    def get_service_json(self) -> dict:
        """Get metric service metadata in JSON format."""
        with open(self.config_file, "r") as file:
            return json.load(file)

    def get_service_summary(self) -> str:
        """Get a summary of the metric service metadata."""
        service_json = self.get_service_json()
        service_name = service_json.get("Name", "")
        namespace = service_json.get("Namespace", "")
        desc = service_json.get("Desc", "")
        supported_operations = service_json.get("Supported Operations", [])
        operations_str = "\n".join([f"  - {op}" for op in supported_operations])

        return (
            f"Telemetry Service Name: {service_name}\n"
            f"Namespace: {namespace}\n"
            f"Description: {desc}\n"
            f"Supported Operations:\n{operations_str}"
        )

    def deploy(self):
        """Deploy the metric collector using Helm."""
        if self._is_prometheus_running():
            print("Prometheus is already running. Skipping redeployment.")
            return

        self._delete_pv()
        Helm.uninstall(**self.helm_configs)

        if self.pv_config_file:
            pv_name = self._get_pv_name_from_file(self.pv_config_file)
            if not self._pv_exists(pv_name):
                self._apply_pv()

        Helm.install(**self.helm_configs)
        print("Waiting for 30 seconds to allow the Prometheus deployment to finish...")
        time.sleep(30)
        Helm.assert_if_deployed(self.namespace)

    def teardown(self):
        """Teardown the metric collector deployment."""
        Helm.uninstall(**self.helm_configs)

        if self.pv_config_file:
            self._delete_pv()

    def _apply_pv(self):
        """Apply the PersistentVolume configuration."""
        print(f"Applying PersistentVolume from {self.pv_config_file}")
        KubeCtl().exec_command(
            f"kubectl apply -f {self.pv_config_file} -n {self.namespace}"
        )

    def _delete_pv(self):
        """Delete the PersistentVolume and associated PersistentVolumeClaim."""
        pv_name = self._get_pv_name_from_file(self.pv_config_file)
        result = KubeCtl().exec_command(f"kubectl get pv {pv_name} --ignore-not-found")

        if result:
            print(f"Deleting PersistentVolume {pv_name}")
            KubeCtl().exec_command(f"kubectl delete pv {pv_name}")
            print(f"Successfully deleted PersistentVolume from {pv_name}")
        else:
            print(f"PersistentVolume {pv_name} not found. Skipping deletion.")

    def _get_pv_name_from_file(self, pv_config_file):
        """Extract PV name from the configuration file."""
        with open(pv_config_file, "r") as file:
            pv_config = yaml.safe_load(file)
            return pv_config["metadata"]["name"]

    def _pv_exists(self, pv_name: str) -> bool:
        """Check if the PersistentVolume exists."""
        command = f"kubectl get pv {pv_name}"
        try:
            result = KubeCtl().exec_command(command)
            if "No resources found" in result or "Error" in result:
                return False
        except CalledProcessError as e:
            return False
        return True

    def _is_prometheus_running(self) -> bool:
        """Check if Prometheus is already running in the cluster."""
        command = (
            f"kubectl get pods -n {self.namespace} -l app.kubernetes.io/name=prometheus"
        )
        try:
            result = KubeCtl().exec_command(command)
            if "Running" in result:
                return True
        except CalledProcessError:
            return False
        return False