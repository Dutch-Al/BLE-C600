"""Config flow for C600 BlE integration."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from .BLE_C600 import C600BluetoothDeviceData, C600Device
from bleak import BleakError
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    name: str
    discovery_info: BluetoothServiceInfo
    device: C600Device


def get_name(device: C600Device) -> str:
    """Generate name with identifier for device."""

    return f"{device.name}"


class C600DeviceUpdateError(Exception):
    """Custom error class for device updates."""


class C600ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for C600 BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: Discovery | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    async def _get_device_data(
        self, discovery_info: BluetoothServiceInfo
    ) -> C600Device:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, discovery_info.address
        )
        _LOGGER.debug("in _get_device_data")
        if ble_device is None:
            _LOGGER.debug("no ble_device in _get_device_data")
            raise C600DeviceUpdateError("No ble_device")
        
        _LOGGER.debug("Getting Device")
        c600 = C600BluetoothDeviceData(_LOGGER)
        _LOGGER.debug("Got Device Device")
        try:
            _LOGGER.debug("Try Update")
            data = await c600.update_device(ble_device)
            _LOGGER.debug("Got Data")
            #data.name = discovery_info.advertisement.local_name
            data.name = discovery_info.address
            data.address = discovery_info.address
            data.identifier = discovery_info.advertisement.local_name
        except BleakError as err:
            _LOGGER.error(
                "Error connecting to and getting data from %s: %s",
                discovery_info.address,
                err,
            )
            raise C600DeviceUpdateError("Failed getting device data") from err
        except Exception as err:
            _LOGGER.error(
                "Unknown error occurred from %s: %s", discovery_info.address, err
            )
            raise err
        return data

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Discovered BT device: %s", discovery_info)
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        try:
            device = await self._get_device_data(discovery_info)
        except C600DeviceUpdateError:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # pylint: disable=broad-except
            return self.async_abort(reason="unknown")

        name = get_name(device)
        self.context["title_placeholders"] = {"name": name}
        self._discovered_device = Discovery(name, discovery_info, device)

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"], data={}
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovery = self._discovered_devices[address]

            self.context["title_placeholders"] = {
                "name": discovery.name,
            }

            self._discovered_device = discovery

            return self.async_create_entry(title=discovery.name, data={})

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue

            ##

            if discovery_info.advertisement.local_name is None:
                continue

            if not (
                discovery_info.advertisement.local_name.startswith("BLE-C600")
            ):
                continue

            _LOGGER.debug("Found My Device")
            _LOGGER.debug("C600 Discovery address: %s", address)
            _LOGGER.debug("C600 Man Data: %s", discovery_info.manufacturer_data)
            _LOGGER.debug("C600 advertisement: %s", discovery_info.advertisement)
            _LOGGER.debug("C600 device: %s", discovery_info.device)
            _LOGGER.debug("C600 service data: %s", discovery_info.service_data)
            _LOGGER.debug("C600 service uuids: %s", discovery_info.service_uuids)
            _LOGGER.debug("C600 rssi: %s", discovery_info.rssi)
            _LOGGER.debug(
                "C600 advertisement: %s", discovery_info.advertisement.local_name
            )
            try:
                device = await self._get_device_data(discovery_info)
                _LOGGER.debug("Getting Device Data")
            except C600DeviceUpdateError:
                _LOGGER.debug("Cannot Connect")
                return self.async_abort(reason="cannot_connect")
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("Cannot Connect - Unknown")
                return self.async_abort(reason="unknown")
            _LOGGER.debug("Getting Name")
            name = get_name(device)
            self._discovered_devices[address] = Discovery(name, discovery_info, device)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        titles = {
            address: get_name(discovery.device)
            for (address, discovery) in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(titles),
                },
            ),
        )
