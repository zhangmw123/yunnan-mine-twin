import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres123@localhost:5433/yunnan_mine_gis",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")
MINE_CENTER_LAT = float(os.getenv("MINE_CENTER_LAT", "24.715"))
MINE_CENTER_LNG = float(os.getenv("MINE_CENTER_LNG", "102.562"))

# 三色预警阈值 (GB/T 51214)
THRESHOLD_BLUE = 3.0   # 关注 mm/d
THRESHOLD_ORANGE = 5.0  # 橙色预警 mm/d
THRESHOLD_RED = 8.0    # 红色滑坡告警 mm/d
