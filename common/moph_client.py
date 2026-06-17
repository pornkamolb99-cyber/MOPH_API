from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from common.config import (
    MophConfig,
    get_moph_config,
    get_fdh_config,
    get_cancer_link_config,
    get_cancer_anywhere_config,
    get_sbh_oncloud_config
)


@dataclass
class ApiResult:
    ok: bool
    status_code: int | None
    data: dict[str, Any] | list[Any] | None
    text: str

    def get(self, key: str, default: Any = None) -> Any:
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default


class MophApiClient:
    def __init__(self, config: MophConfig | None = None, timeout: int = 60, verify_ssl: bool = False) -> None:
        self.config = config or get_moph_config()
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._token: str | None = None

    def get_token(self) -> str:
        if self._token:
            return self._token

        payload = {
            "hospital_code": self.config.token_hospital_code,
            "user": self.config.token_user,
            "password_hash": self.config.token_password_hash,
        }

        response = requests.post(
            self.config.token_url,
            json=payload,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()

        token = self._extract_token(response.text.strip())
        if not token:
            raise ValueError("ขอ token สำเร็จ แต่ไม่พบ token ใน response")

        self._token = token
        return token

    @staticmethod
    def _extract_token(text: str) -> str:
        try:
            data = requests.models.complexjson.loads(text)
        except ValueError:
            return text.strip().strip('"')

        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            return (
                data.get("access_token")
                or data.get("token")
                or data.get("result", {}).get("access_token")
                or data.get("result", {}).get("token")
                or data.get("data", {}).get("access_token")
                or data.get("data", {}).get("token")
                or ""
            )

        return ""

    def post_json(self, url: str, payload: dict[str, Any]) -> ApiResult:
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.get_token()}",
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))

    def get_fdh_token(self) -> str:
        config = get_fdh_config()

        payload = {
            "user": config.token_user,
            "password_hash": config.token_password_hash,
            "hospital_code": config.token_hospital_code,
        }

        response = requests.post(
            config.token_url,
            json=payload,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()

        return self._extract_token(response.text.strip())

    def send_506(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_json(self.config.send_506_url, payload)

    def send_epi(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_json(self.config.send_epi_url, payload)

    def send_dm(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_json(self.config.dm_url, payload)

    def send_dt(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_json(self.config.send_dt_url, payload)

    def update_immunization(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_json(self.config.update_immunization_url, payload)

    def update_lab(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_json(self.config.update_lab_url, payload)

    def post_cancer_link_json(self, url: str, payload: list[dict[str, Any]]) -> ApiResult:
        config = get_cancer_link_config()

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "hospitalKey": config.hospital_key,
            config.secret_header_name: config.secret_header_value,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))

    def send_cancer_link_service(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().service_url, payload)

    def send_cancer_link_patient(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().patient_url, payload)

    def send_cancer_link_admission(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().admission_url, payload)

    def send_cancer_link_diagnosis_opd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().diagnosis_opd_url, payload)

    def send_cancer_link_diagnosis_ipd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().diagnosis_ipd_url, payload)

    def send_cancer_link_procedure_opd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().procedure_opd_url, payload)

    def send_cancer_link_procedure_ipd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().procedure_ipd_url, payload)

    def send_cancer_link_drug_opd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().drug_opd_url, payload)

    def send_cancer_link_drug_ipd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().drug_ipd_url, payload)

    def send_cancer_link_lab_opd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().lab_opd_url, payload)

    def send_cancer_link_lab_ipd(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().lab_ipd_url, payload)

    def send_cancer_link_death(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().death_url, payload)

    def send_cancer_link_spacial_pp(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().spacial_pp_url, payload)

    def send_cancer_link_lab_fu(self, payload: list[dict[str, Any]]) -> ApiResult:
        return self.post_cancer_link_json(get_cancer_link_config().lab_fu_url, payload)

    def post_cancer_anywhere_json(self, url: str, payload: dict[str, Any]) -> ApiResult:
        config = get_cancer_anywhere_config()
    

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "Authorization": config.authorization,
        }

        if config.cookie:
            headers["Cookie"] = config.cookie

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))

    def send_cancer_diag(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_cancer_anywhere_json(
            get_cancer_anywhere_config().diag_url,
            payload,
        )
    
    def send_cancer_patient(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_cancer_anywhere_json(
            get_cancer_anywhere_config().patient_url,
            payload,
        )

    def send_cancer_treatment(self, payload: dict[str, Any]) -> ApiResult:
        return self.post_cancer_anywhere_json(
            get_cancer_anywhere_config().treatment_url,
            payload,
        )

    def send_sbh_oncloud_aipn(
        self,
        payload: list[dict[str, Any]]
    ) -> ApiResult:

        config = get_sbh_oncloud_config()

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-Api-Key": config.api_key,
        }

        try:
            response = requests.post(
                config.aipn_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(
                ok=False,
                status_code=None,
                data=None,
                text=str(exc),
            )
    
    def send_sbh_oncloud_cipn(self, payload: list[dict[str, Any]]) -> ApiResult:
        config = get_sbh_oncloud_config()

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-Api-Key": config.api_key,
        }

        try:
            response = requests.post(
                config.cipn_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))

    def send_sbh_oncloud_fire(self, payload: list[dict[str, Any]]) -> ApiResult:
        config = get_sbh_oncloud_config()

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-Api-Key": config.fire_api_key,
    }

        try:
            response = requests.post(
                config.fire_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            verify=self.verify_ssl,
            )   

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))
    def send_sbh_oncloud_hrm_nurse(self, payload: list[dict[str, Any]]) -> ApiResult:
        config = get_sbh_oncloud_config()

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-Api-Key": config.hrm_nurse_api_key,
    }

        try:
            response = requests.post(
                config.hrm_nurse_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))

    def send_sbh_oncloud_uc(self, payload: list[dict[str, Any]]) -> ApiResult:
        config = get_sbh_oncloud_config()

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
            "X-Api-Key": config.uc_api_key,
    }

        try:
            response = requests.post(
                config.uc_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
        )

            try:
                data = response.json()
            except ValueError:
                data = None

            return ApiResult(
                ok=response.ok,
                status_code=response.status_code,
                data=data,
                text=response.text,
            )

        except requests.RequestException as exc:
            return ApiResult(ok=False, status_code=None, data=None, text=str(exc))