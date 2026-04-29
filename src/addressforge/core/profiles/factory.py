from __future__ import annotations
from typing import Dict
from .base import BaseCountryProfile
from .canada import CanadaProfile

# Global registry of available country profiles
# 国家配置文件的全局注册表
_PROFILES: Dict[str, BaseCountryProfile] = {
    "CA": CanadaProfile(),
}

_PROFILE_ALIASES: Dict[str, str] = {
    "BASE_CANADA": "CA",
    "NORTH_AMERICA_DEFAULT": "CA",
    "CUSTOM": "CA",
}

def get_profile(country_code: str = "CA") -> BaseCountryProfile:
    """
    Retrieves the singleton instance of a country profile.
    获取国家配置文件的单例实例。
    
    :param country_code: ISO alpha-2 country code. Default is 'CA'.
    :param country_code: ISO alpha-2 国家代码。默认为 'CA'。
    :return: An implementation of BaseCountryProfile.
    :return: BaseCountryProfile 的一个实现。
    """
    code = country_code.upper()
    code = _PROFILE_ALIASES.get(code, code)
    if code not in _PROFILES:
        # Fallback to Canada if the specified country is not yet supported
        # 如果指定的国家尚不支持，则回退到加拿大
        return _PROFILES["CA"]
    return _PROFILES[code]

def get_active_profile() -> BaseCountryProfile:
    """
    Helper to get the profile for the current system configuration.
    获取当前系统配置对应的配置文件的辅助函数。
    """
    # In the future, this could read from environment variables or workspace settings
    # 未来，这可以从环境变量或工作空间设置中读取
    import os
    target_country = os.getenv("ADDRESSFORGE_COUNTRY", "CA")
    return get_profile(target_country)
