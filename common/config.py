from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    server: str
    database: str
    username: str
    password: str
    driver: str


@dataclass(frozen=True)
class HospitalConfig:
    code: str
    name: str
    his_identifier: str


@dataclass(frozen=True)
class MophConfig:
    token_url: str
    token_hospital_code: str
    token_user: str
    token_password_hash: str
    send_506_url: str
    send_epi_url: str
    dm_url: str
    send_dt_url: str
    update_immunization_url: str
    update_lab_url: str

@dataclass(frozen=True)
class FdhConfig:
    token_url: str
    token_hospital_code: str
    token_user: str
    token_password_hash: str
    
@dataclass(frozen=True)
class CancerLinkConfig:
    patient_url: str
    service_url: str
    admission_url: str
    diagnosis_opd_url: str
    diagnosis_ipd_url: str
    procedure_opd_url: str
    procedure_ipd_url: str
    drug_opd_url: str
    drug_ipd_url: str
    lab_opd_url: str
    lab_ipd_url: str
    death_url: str
    spacial_pp_url: str
    lab_fu_url: str
    hospital_key: str
    secret_header_name: str
    secret_header_value: str

@dataclass(frozen=True)
class CancerAnywhereConfig:
    diag_url: str
    patient_url: str
    treatment_url: str
    authorization: str
    cookie: str

@dataclass(frozen=True)
class SbhOnCloudConfig:
    aipn_url: str
    cipn_url: str
    api_key: str
    fire_url: str
    fire_api_key: str
    hrm_nurse_url: str
    hrm_nurse_api_key: str
    uc_url: str
    uc_api_key: str

def get_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        server=os.getenv("DB_SERVER", "10.0.1.1,1433"),
        database=os.getenv("DB_NAME", "SSBDatabase"),
        username=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        driver=os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
    )


def get_hospital_config() -> HospitalConfig:
    return HospitalConfig(
        code=os.getenv("HOSPITAL_CODE", "10661"),
        name=os.getenv("HOSPITAL_NAME", "โรงพยาบาลสระบุรี"),
        his_identifier=os.getenv("HIS_IDENTIFIER", "HIS Vendor A version 1.0"),
    )


def get_moph_config() -> MophConfig:
    return MophConfig(
        token_url=os.getenv("MOPH_TOKEN_URL", "https://cvp1.moph.go.th/token?Action=get_moph_access_token"),
        token_hospital_code=os.getenv("MOPH_TOKEN_HOSPITAL_CODE", "10661"),
        token_user=os.getenv("MOPH_TOKEN_USER", ""),
        token_password_hash=os.getenv("MOPH_TOKEN_PASSWORD_HASH", ""),
        send_506_url=os.getenv("MOPH_SEND_506_URL", "https://epidemcenter.moph.go.th/epidem506/api/Send506"),
        send_epi_url=os.getenv("MOPH_SEND_EPI_URL", "https://claim-nhso.moph.go.th/api/v1/opd/service-admissions/epi"),
        send_dm_url=os.getenv("MOPH_SEND_DM_URL", "https://claim-nhso.moph.go.th/api/v1/opd/service-admissions/dmht"),
        send_dt_url=os.getenv("MOPH_SEND_DT_URL", "https://claim-nhso.moph.go.th/api/v1/opd/service-admissions/dt"),
        update_immunization_url=os.getenv("MOPH_UPDATE_IMMUNIZATION_URL", "https://cloud4.hosxp.net/api/moph/UpdateImmunization"),
        update_lab_url=os.getenv("MOPH_UPDATE_LAB_URL", "https://cvp1.moph.go.th/api/UpdateLab"),
    )

def get_fdh_config() -> FdhConfig:
    return FdhConfig(
        token_url=os.getenv("FDH_TOKEN_URL", "https://fdh.moph.go.th/token?Action=get_moph_access_token"),
        token_hospital_code=os.getenv("FDH_TOKEN_HOSPITAL_CODE", "10661"),
        token_user=os.getenv("FDH_TOKEN_USER", ""),
        token_password_hash=os.getenv("FDH_TOKEN_PASSWORD_HASH", ""),
    )
    
def get_cancer_link_config() -> CancerLinkConfig:
    return CancerLinkConfig(
        patient_url=os.getenv("CANCER_LINK_PATIENT_URL", ""),
        service_url=os.getenv("CANCER_LINK_SERVICE_URL", ""),
        admission_url=os.getenv("CANCER_LINK_ADMISSION_URL", ""),
        diagnosis_opd_url=os.getenv("CANCER_LINK_DIAGNOSIS_OPD_URL", ""),
        diagnosis_ipd_url=os.getenv("CANCER_LINK_DIAGNOSIS_IPD_URL", ""),
        procedure_opd_url=os.getenv("CANCER_LINK_PROCEDURE_OPD_URL", ""),
        procedure_ipd_url=os.getenv("CANCER_LINK_PROCEDURE_IPD_URL", ""),
        drug_opd_url=os.getenv("CANCER_LINK_DRUG_OPD_URL", ""),
        drug_ipd_url=os.getenv("CANCER_LINK_DRUG_IPD_URL", ""),
        lab_opd_url=os.getenv("CANCER_LINK_LAB_OPD_URL", ""),
        lab_ipd_url=os.getenv("CANCER_LINK_LAB_IPD_URL", ""),
        death_url=os.getenv("CANCER_LINK_DEATH_URL", ""),
        spacial_pp_url=os.getenv("CANCER_LINK_SPACIAL_PP_URL", ""),
        lab_fu_url=os.getenv("CANCER_LINK_LAB_FU_URL", ""),
        hospital_key=os.getenv("CANCER_LINK_HOSPITAL_KEY", ""),
        secret_header_name=os.getenv("CANCER_LINK_SECRET_HEADER_NAME", ""),
        secret_header_value=os.getenv("CANCER_LINK_SECRET_HEADER_VALUE", ""),
    )

def get_cancer_anywhere_config() -> CancerAnywhereConfig:
    return CancerAnywhereConfig(
        diag_url=os.getenv("CANCER_DIAG_URL", ""),
        patient_url=os.getenv("CANCER_PATIENT_URL", ""),
        treatment_url=os.getenv("CANCER_TREATMENT_URL", ""),
        authorization=os.getenv("CANCER_DIAG_AUTHORIZATION", ""),
        cookie=os.getenv("CANCER_DIAG_COOKIE", ""),
    )

def get_sbh_oncloud_config() -> SbhOnCloudConfig:
    return SbhOnCloudConfig(
        aipn_url=os.getenv("SBH_ONCLOUD_AIPN_URL", ""),
        cipn_url=os.getenv("SBH_ONCLOUD_CIPN_URL", ""),
        uc_url=os.getenv("SBH_ONCLOUD_UC_URL", ""),
        api_key=os.getenv("SBH_ONCLOUD_API_KEY", ""),
        fire_url=os.getenv("SBH_ONCLOUD_FIRE_URL", ""),
        fire_api_key=os.getenv("SBH_ONCLOUD_FIRE_API_KEY", ""),
        hrm_nurse_url=os.getenv("SBH_ONCLOUD_HRM_NURSE_URL", ""),
        hrm_nurse_api_key=os.getenv("SBH_ONCLOUD_HRM_NURSE_API_KEY", ""),

    )