# utils.py
import hashlib
import logging
import os
import re
from pathlib import Path

import mysql.connector
import numpy as np
from mysql.connector import Error
from scipy.stats import entropy

from .config import (
    INVALID_ROWS_FILE,
    LOG_FILE,
    MYSQL_CONFIG,
    NS_GPS_BOUNDS,
    POSTAL_CODE_PATTERN,
    SALT,
)
from .profiles.base import BaseCountryProfile
from .profiles.factory import get_profile

# 设置日志
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger(__name__)

def _resolve_profile(
    profile: BaseCountryProfile | str | None = None,
    *,
    country_code: str = "CA",
) -> BaseCountryProfile:
    if isinstance(profile, BaseCountryProfile):
        return profile
    if isinstance(profile, str) and profile.strip():
        return get_profile(profile.strip())
    return get_profile(country_code)

# 数据库连接
def get_db_connection():
    """获取 MySQL 连接"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        logger.error(f"MySQL 连接错误: {e}")
        raise

# 验证 GPS
def is_valid_gps(lat, lon, profile: BaseCountryProfile | str | None = None, *, country_code: str = "CA"):
    """
    Validates if GPS coordinates are within the bounds of the active profile.
    验证 GPS 坐标是否在活动配置文件的边界内。
    """
    bounds = _resolve_profile(profile, country_code=country_code).gps_bounds
    try:
        lat = float(lat)
        lon = float(lon)
        return (bounds['lat_min'] <= lat <= bounds['lat_max'] and
                bounds['lon_min'] <= lon <= bounds['lon_max'] and
                not (np.isnan(lat) or np.isnan(lon)))
    except (ValueError, TypeError):
        return False

# 验证邮编
def is_valid_postal_code(postal_code, profile: BaseCountryProfile | str | None = None, *, country_code: str = "CA"):
    """
    Validates the postal code format against the active profile's pattern.
    根据活动配置文件的模式验证邮政编码格式。
    """
    if not postal_code:
        return False
    pattern = _resolve_profile(profile, country_code=country_code).postal_code_pattern
    return bool(re.match(pattern, postal_code.strip()))


# 生成用户脱敏哈希
def generate_user_hash(user_name, user_phone):
    """生成 user_hash_key = SHA256(user_name + user_phone + SALT)"""
    if not user_name:
        return None
    input_string = f"{user_name}{user_phone}{SALT}"
    return hashlib.sha256(input_string.encode('utf-8')).hexdigest()

# 计算置信度
def calculate_confidence(frequencies):
    """计算 unit_number 置信度：(max_frequency / total) * (1 - entropy_factor)"""
    if not frequencies:
        return 0.0
    total = sum(frequencies)
    max_freq = max(frequencies)
    entropy_factor = entropy(frequencies) / np.log(len(frequencies)) if len(frequencies) > 1 else 0
    return (max_freq / total) * (1 - entropy_factor)

# 保存无效行
def save_invalid_row(row, file=INVALID_ROWS_FILE):
    """保存无效行到 CSV"""
    import pandas as pd
    try:
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([row])
        df.to_csv(file, mode='a', header=not os.path.exists(file), index=False)
        order_id = row.get('order_id') or '未知'
        logger.info("已记录无效订单，order_id=%s", order_id)
    except Exception as e:
        logger.error(f"保存无效行失败: {e}")

# 数据库插入（通用）
def execute_insert_query(query, data, single_row=False):
    """执行插入/更新查询"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if single_row:
            cursor.execute(query, data)
        else:
            cursor.executemany(query, data)
        conn.commit()
        return cursor.rowcount
    except Error as e:
        logger.error(f"插入失败: {e}, 数据: {data}")
        conn.rollback()
        return 0
    finally:
        cursor.close()
        conn.close()
